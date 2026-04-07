# diag_smule_browser_download.py

import asyncio

from smule_extract_diag_variant import _extract_with_browser, extract_smule
from smule_download import download_smule_file, pick_smule_media

# === НАСТРОЙКИ ===
URL = "https://www.smule.com/sing-recording/2629090486_5190271116"   # вставь сюда
PROXY = "http://gnktxrqy:munhcy6msboc@72.1.136.146:7037"
# =================


async def main():
    print("=== EXTRACT ===")
    extract = await extract_smule(URL, keep_browser_open=True)

    if not extract or not extract.get("ok"):
        print("extract failed")
        return

    print(f"proxy_used={extract.get('proxy')}")

    mode, media_url = pick_smule_media(extract)
    print(f"media_url={media_url}")
    print(f"mode={mode}")

    # --- ТЕСТ 1: aiohttp ---
    print("\n=== TEST aiohttp ===")
    try:
        path = await download_smule_file(
            media_url,
            mode,
            proxy=PROXY
        )
        print(f"aiohttp OK: {path}")
    except Exception as e:
        print(f"aiohttp FAIL: {e}")

    # --- ТЕСТ 2: browser context ---
    print("\n=== TEST browser ===")
    page = extract.get("page")
    if not page:
        print("no page in extract")
        return

    try:
        resp = await page.request.get(media_url)
        print(f"browser status={resp.status}")

        if resp.ok:
            data = await resp.body()
            ext = ".m4a" if mode == "audio" else ".mp4"
            out_name = f"diag_browser_download{ext}"
            with open(out_name, "wb") as f:
                f.write(data)
            print(f"browser OK, bytes={len(data)} saved_to={out_name}")
        else:
            print("browser FAIL")

    except Exception as e:
        print(f"browser exception: {e}")


if __name__ == "__main__":
    asyncio.run(main())