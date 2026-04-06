import asyncio
from playwright.async_api import async_playwright

URL = "https://www.smule.com/sing-recording/2629090486_5197369075"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        media_urls = []

        # ловим все сетевые запросы
        page.on("request", lambda req: (
            media_urls.append(req.url)
            if (".m4a" in req.url or ".mp4" in req.url or ".m3u8" in req.url)
            else None
        ))

        await page.goto(URL, timeout=60000)

        # ждем пока страница "оживет"
        await page.wait_for_timeout(5000)

        print("FOUND MEDIA:")
        for url in set(media_urls):
            print(url)

        await browser.close()

asyncio.run(main())
