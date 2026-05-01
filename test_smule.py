import asyncio
from smule_extract_browser_session import extract_smule, download_smule_file_in_browser, close_smule_browser_extract
from smule_download import pick_smule_media

async def test():
    url = "https://www.smule.com/sing-recording/2327427123_5203980702"
    
    extract = await extract_smule(url, keep_browser_open=True)
    print(f"ok={extract.get('ok')} perf={extract.get('perf')} proxy={extract.get('proxy')}")
    
    mode, media_url = pick_smule_media(extract, preferred_mode="audio")
    print(f"mode={mode} media_url={media_url}")
    
    if not media_url:
        print("NO MEDIA URL")
        await close_smule_browser_extract(extract)
        return
    
    try:
        path = await download_smule_file_in_browser(extract, media_url, mode)
        print(f"SUCCESS path={path}")
    finally:
        await close_smule_browser_extract(extract)

asyncio.run(test())