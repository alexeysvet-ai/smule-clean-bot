import os
import tempfile
from playwright.async_api import async_playwright
from proxy import get_active_proxies


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
                page = await browser.new_page()
                media_urls = set()

                def on_request(req):
                    u = req.url
                    if ".m4a" in u or ".mp4" in u or ".m3u8" in u:
                        media_urls.add(u)

                page.on("request", on_request)

                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(3000)

                try:
                    await page.click("text=Accept Cookies", timeout=3000)
                except:
                    pass

                await page.wait_for_timeout(5000)

                perf = await page.evaluate("""
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
                """)

                await browser.close()
                return perf, list(media_urls)

        page = await browser.new_page()
        media_urls = set()

        def on_request(req):
            u = req.url
            if ".m4a" in u or ".mp4" in u or ".m3u8" in u:
                media_urls.add(u)

        page.on("request", on_request)

        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3000)

        try:
            await page.click("text=Accept Cookies", timeout=3000)
        except:
            pass

        await page.wait_for_timeout(5000)

        perf = await page.evaluate("""
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
        """)

        return perf, list(media_urls), page, browser, playwright

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
                perf, media, page, browser, playwright = await _extract_with_browser(
                    url,
                    proxy_cfg,
                    keep_browser_open=True
                )

                if perf or media:
                    return {
                        "ok": True,
                        "perf": perf,
                        "media": media,
                        "proxy": proxy,
                        "page": page,
                        "browser": browser,
                        "playwright": playwright,
                    }
            else:
                perf, media = await _extract_with_browser(url, proxy_cfg)

                if perf or media:
                    return {
                        "ok": True,
                        "perf": perf,
                        "media": media,
                        "proxy": proxy,
                    }

        except Exception as e:
            print(f"[SMULE PROXY FAIL] {proxy} err={e}")

    return {"ok": False, "reason": "no_working_proxy"}


async def download_smule_file_in_browser(extract: dict, media_url: str, mode: str) -> str:
    page = extract.get("page")
    if not page:
        raise RuntimeError("Browser page not available")

    suffix = ".m4a" if mode == "audio" else ".mp4"
    fd, temp_path = tempfile.mkstemp(prefix="smule_browser_", suffix=suffix)
    os.close(fd)

    print(
        f"[SMULE BROWSER DOWNLOAD TRY] "
        f"mode={mode} proxy={extract.get('proxy')} media_url={media_url}"
    )

    try:
        resp = await page.request.get(media_url)
        if not resp.ok:
            raise RuntimeError(f"{resp.status} {resp.status_text}")

        data = await resp.body()
        with open(temp_path, "wb") as f:
            f.write(data)

        return temp_path
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


async def close_smule_browser_extract(extract: dict):
    page = extract.get("page")
    browser = extract.get("browser")
    playwright = extract.get("playwright")

    try:
        if page is not None:
            await page.close()
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
