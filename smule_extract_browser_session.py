import os
import tempfile
from playwright.async_api import async_playwright
from proxy import get_active_proxies
from config import DOWNLOAD_TIMEOUT
from logger import log_mem
from curl_cffi.requests import AsyncSession

def build_proxy_config(proxy: str) -> dict:
    raw = proxy.strip()

    if "://" not in raw:
        raw = f"http://{raw}"

    scheme, rest = raw.split("://", 1)

    if "@" in rest:
        auth, hostport = rest.split("@", 1)
        username, password = auth.split(":", 1)
        return {
            "server": f"{scheme}://{hostport}",
            "username": username,
            "password": password,
        }

    return {"server": f"{scheme}://{rest}"}


async def _has_smule_result(page, media_urls: set) -> bool:
    if media_urls:
        return True

    return await page.evaluate(
        """
        () => {
          const p = window?.DataStore?.Pages?.Recording?.performance || null;
          return Boolean(
            p?.media_url ||
            p?.video_media_url ||
            p?.video_media_mp4_url ||
            p?.perf_status === "processing"
          );
        }
        """
    )


async def _wait_for_smule_result(page, media_urls: set, timeout_ms: int) -> bool:
    if await _has_smule_result(page, media_urls):
        return True

    try:
        await page.wait_for_function(
            """
            () => {
              const p = window?.DataStore?.Pages?.Recording?.performance || null;
              return Boolean(
                p?.media_url ||
                p?.video_media_url ||
                p?.video_media_mp4_url ||
                p?.perf_status === "processing"
              );
            }
            """,
            timeout=timeout_ms,
        )
        return True
    except Exception:
        return bool(media_urls)


async def _open_page(browser, url: str):
    print(f"[SMULE OPEN PAGE START] url={url}")
    context = await browser.new_context(accept_downloads=True)
    print(f"[SMULE OPEN PAGE CONTEXT OK] url={url}")

    page = await context.new_page()
    print(f"[SMULE OPEN PAGE NEW PAGE OK] url={url}")

    media_urls = set()

    def on_request(req):
        u = req.url
        if ".m4a" in u or ".mp4" in u or ".m3u8" in u:
            media_urls.add(u)

    page.on("request", on_request)
    print(f"[SMULE OPEN PAGE BEFORE GOTO] url={url}")

    await page.goto(url, wait_until="domcontentloaded", timeout=6000)
    print(f"[SMULE OPEN PAGE AFTER GOTO] url={url}")

    ready = await _wait_for_smule_result(page, media_urls, timeout_ms=3000)
    print(f"[SMULE OPEN PAGE WAIT_FAST] url={url} ready={ready} media_count={len(media_urls)}")

    if not ready:
        try:
            await page.click("text=Accept Cookies", timeout=1000)
            print(f"[SMULE OPEN PAGE COOKIE CLICKED] url={url}")
        except Exception as e:
            print(f"[SMULE OPEN PAGE COOKIE SKIP] url={url} error={e}")

        ready = await _wait_for_smule_result(page, media_urls, timeout_ms=5000)
        print(f"[SMULE OPEN PAGE WAIT_FINAL] url={url} ready={ready} media_count={len(media_urls)}")

    perf = await page.evaluate(
        """
        () => {
          const p = window?.DataStore?.Pages?.Recording?.performance || null;
          if (!p) return null;
          return {
            title: p.title ?? null,
            artist: p.artist ?? null,
            perf_type: p.type ?? null,
            perf_status: p.perf_status ?? null,
            media_url: p.media_url ?? null,
            video_media_url: p.video_media_url ?? null,
            video_media_mp4_url: p.video_media_mp4_url ?? null
          };
        }
        """
    )
    print(f"[SMULE OPEN PAGE PERF READY] url={url} has_perf={bool(perf)} media_count={len(media_urls)}")

    return perf, list(media_urls), context, page


async def _extract_with_browser(url: str, proxy_cfg: dict, keep_browser_open: bool = False):
    if keep_browser_open:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=True,
            proxy=proxy_cfg
        )
    else:
        playwright = None
        browser = None

    try:
        if browser is None:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    proxy=proxy_cfg
                )
                perf, media, context, page = await _open_page(browser, url)
                await page.close()
                await context.close()
                await browser.close()
                return perf, media

        perf, media, context, page = await _open_page(browser, url)
        return perf, media, context, page, browser, playwright

    except Exception:
        if browser is not None:
            await browser.close()
        if playwright is not None:
            await playwright.stop()
        raise


async def extract_smule(url: str, keep_browser_open: bool = False) -> dict:
    proxies = get_active_proxies()

    if not proxies:
        return {"ok": False, "reason": "no_proxies"}

    for proxy in proxies:
        try:
            proxy_cfg = build_proxy_config(proxy)

            if keep_browser_open:
                perf, media, context, page, browser, playwright = await _extract_with_browser(
                    url,
                    proxy_cfg,
                    keep_browser_open=True
                )

                return {
                    "ok": True,
                    "perf": perf,
                    "media": media,
                    "proxy": proxy,
                    "context": context,
                    "page": page,
                    "browser": browser,
                    "playwright": playwright,
                    "reason": None if (perf or media) else "no_media_on_page",
                }

            perf, media = await _extract_with_browser(url, proxy_cfg)

            return {
                "ok": True,
                "perf": perf,
                "media": media,
                "proxy": proxy,
                "reason": None if (perf or media) else "no_media_on_page",
            }

        except Exception as e:
            print(f"[SMULE PROXY FAIL] {proxy} err={e}")

    return {"ok": False, "reason": "no_working_proxy"}

async def download_smule_file_in_browser(extract: dict, media_url: str, mode: str) -> str:
    context = extract.get("context")
    page = extract.get("page")
    proxy = extract.get("proxy")

    if not context or not page:
        raise RuntimeError("Browser context/page not available")

    suffix = ".m4a" if mode == "audio" else ".mp4"
    fd, temp_path = tempfile.mkstemp(prefix="smule_dl_", suffix=suffix)
    os.close(fd)

    print(f"[CURL STREAM] mode={mode} proxy={proxy} media_url={media_url}")

    try:
        # Берём куки и UA из живого браузерного контекста
        cookies_list = await context.cookies()
        cookies = {c["name"]: c["value"] for c in cookies_list}
        user_agent = await page.evaluate("() => navigator.userAgent")
        
        page_url = page.url

        print(f"[CURL STREAM] cookie_names={list(cookies.keys())} ua={user_agent[:60]}")
        print(f"[CURL STREAM] browser_proxy={proxy}")

        headers = {
            "User-Agent": user_agent,
            "Referer": page_url,
            "Origin": "https://www.smule.com",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        }


        async with AsyncSession(impersonate="chrome120") as session:
            resp = await session.get(
                media_url,
                headers=headers,
                cookies=cookies,
                proxies={"https": proxy} if proxy else None,
                stream=True,
            )
            print(f"[CURL STREAM] status={resp.status_code}")
            resp.raise_for_status()

            with open(temp_path, "wb") as f:
                async for chunk in resp.aiter_content(chunk_size=256 * 1024):
                    if chunk:
                        f.write(chunk)

        if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
            raise RuntimeError("Downloaded file is empty")

        return temp_path

    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise

async def close_smule_browser_extract(extract: dict):
    page = extract.get("page")
    context = extract.get("context")
    browser = extract.get("browser")
    playwright = extract.get("playwright")

    try:
        if page is not None:
            await page.close()
    except Exception:
        pass

    try:
        if context is not None:
            await context.close()
    except Exception:
        pass

    try:
        if browser is not None:
            await browser.close()
    except Exception:
        pass

    try:
        if playwright is not None:
            await playwright.stop()
    except Exception:
        pass
