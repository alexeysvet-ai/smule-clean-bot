import asyncio
import contextlib
import os
import sys
from pathlib import Path

import aiohttp
from yarl import URL

from smule_extract_diag_variant import extract_smule
from smule_download import pick_smule_media

# Usage:
#   python diag_smule_browser_session_stream.py <smule_url>
# or set URL below.

SMULE_URL = ""  # optional fallback


def build_cookie_jar(cookies: list, media_url: str) -> aiohttp.CookieJar:
    jar = aiohttp.CookieJar()
    target_url = URL(media_url)

    for c in cookies:
        name = c.get("name")
        value = c.get("value")
        domain = (c.get("domain") or "").lstrip(".")

        if not name:
            continue

        # keep only cookies relevant to target host when domain is present
        if domain and target_url.host and domain not in target_url.host:
            continue

        jar.update_cookies({name: value}, response_url=target_url)

    return jar


async def download_with_browser_session_stream(page, media_url: str, mode: str) -> str:
    cookies = await page.context.cookies()
    user_agent = await page.evaluate("() => navigator.userAgent")
    referer = page.url

    out_dir = Path(".")
    ext = ".m4a" if mode == "audio" else ".mp4"
    out_path = out_dir / f"diag_browser_session_stream{ext}"

    if out_path.exists():
        out_path.unlink()

    timeout = aiohttp.ClientTimeout(total=180, sock_connect=30, sock_read=180)
    headers = {
        "Referer": referer,
        "User-Agent": user_agent,
    }

    jar = build_cookie_jar(cookies, media_url)

    async with aiohttp.ClientSession(
        cookie_jar=jar,
        timeout=timeout,
        headers=headers,
    ) as session:
        async with session.get(media_url) as resp:
            print(f"[STREAM] status={resp.status}")
            print(
                "[STREAM] headers "
                f"content-type={resp.headers.get('Content-Type')} "
                f"content-length={resp.headers.get('Content-Length')} "
                f"accept-ranges={resp.headers.get('Accept-Ranges')}"
            )
            resp.raise_for_status()

            total = 0
            with open(out_path, "wb") as f:
                async for chunk in resp.content.iter_chunked(1024 * 256):
                    if chunk:
                        f.write(chunk)
                        total += len(chunk)
                        print(f"[STREAM] wrote={total} bytes", flush=True)

    if not out_path.exists() or out_path.stat().st_size == 0:
        raise RuntimeError("streamed file is empty")

    print(f"[STREAM] saved_to={out_path} size={out_path.stat().st_size}")
    return str(out_path)


async def main():
    url = sys.argv[1].strip() if len(sys.argv) > 1 else SMULE_URL.strip()
    if not url:
        print("Usage: python diag_smule_browser_session_stream.py <smule_url>")
        return

    print("=== EXTRACT ===")
    extract = await extract_smule(url, keep_browser_open=True)

    if not extract or not extract.get("ok"):
        print(f"extract failed: {extract}")
        return

    print(f"proxy_used={extract.get('proxy')}")

    mode, media_url = pick_smule_media(extract)
    print(f"mode={mode}")
    print(f"media_url={media_url}")

    if not mode or not media_url:
        print("No media_url found")
        return

    page = extract.get("page")
    browser = extract.get("browser")
    playwright = extract.get("playwright")

    if not page:
        print("No page in extract")
        return

    try:
        print("\n=== TEST browser_session_stream ===")
        path = await download_with_browser_session_stream(page, media_url, mode)
        print(f"browser_session_stream OK: {path}")
    except Exception as e:
        print(f"browser_session_stream FAIL: {type(e).__name__}: {e}")
    finally:
        with contextlib.suppress(Exception):
            await page.close()
        with contextlib.suppress(Exception):
            await browser.close()
        with contextlib.suppress(Exception):
            await playwright.stop()


if __name__ == "__main__":
    asyncio.run(main())
