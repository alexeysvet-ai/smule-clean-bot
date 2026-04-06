import asyncio
from playwright.async_api import async_playwright

PROXIES = [
"http://gnktxrqy:munhcy6msboc@72.1.136.146:7037",
"http://gnktxrqy:munhcy6msboc@9.142.37.125:5296",
"http://gnktxrqy:munhcy6msboc@9.142.37.67:5238",
"http://gnktxrqy:munhcy6msboc@63.141.62.165:6458",
"http://gnktxrqy:munhcy6msboc@208.66.76.159:6083",
"http://gnktxrqy:munhcy6msboc@82.29.47.28:7752",
"http://gnktxrqy:munhcy6msboc@140.233.169.116:7833", 
"http://gnktxrqy:munhcy6msboc@130.180.232.213:8651",
"http://gnktxrqy:munhcy6msboc@82.21.33.125:7876",
"http://gnktxrqy:munhcy6msboc@104.253.109.216:5494",
"http://gnktxrqy:munhcy6msboc@62.164.246.54:7779",
"http://gnktxrqy:munhcy6msboc@31.98.7.140:6318",
"http://gnktxrqy:munhcy6msboc@198.145.103.225:6482",
"http://gnktxrqy:munhcy6msboc@193.160.83.17:6338",
"http://gnktxrqy:munhcy6msboc@9.142.36.43:5714",
"http://gnktxrqy:munhcy6msboc@138.226.65.82:7273"
]

URL = "https://www.smule.com/sing-recording/2629090486_5197369075"


def build_proxy_config(proxy: str) -> dict:
    # proxy format: http://user:pass@host:port  или  http://host:port
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

    return {
        "server": f"{scheme}://{rest}",
    }


async def try_proxy(p, proxy: str, idx: int, total: int) -> bool:
    print(f"\n[TRY {idx}/{total}] {proxy}")

    browser = None
    try:
        browser = await p.chromium.launch(
            headless=False,
            proxy=build_proxy_config(proxy),
        )

        page = await browser.new_page()
        media_urls = set()

        def on_request(req):
            req_url = req.url
            if ".m4a" in req_url or ".mp4" in req_url or ".m3u8" in req_url:
                media_urls.add(req_url)
                print("[MEDIA]", req_url)

        page.on("request", on_request)

        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3000)

        try:
            await page.click("text=Accept Cookies", timeout=3000)
            print("[COOKIES ACCEPTED]")
        except:
            print("[NO COOKIE BUTTON]")

        await page.wait_for_timeout(5000)

        print("[URL]", page.url)
        print("[TITLE]", await page.title())

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

        print("[PERF]", perf)

        try:
            await page.mouse.click(320, 380)
            await page.wait_for_timeout(5000)
        except Exception as e:
            print("[CLICK ERROR]", e)

        print("[FOUND MEDIA]")
        for url in sorted(media_urls):
            print(url)

        ok = bool(perf or media_urls)
        print("[RESULT]", "SUCCESS" if ok else "FAIL")
        return ok

    except Exception as e:
        print("[ERROR]", type(e).__name__, e)
        return False

    finally:
        if browser:
            await browser.close()


async def main():
    proxies = PROXIES
    print(f"[PROXIES] loaded={len(proxies)}")

    if not proxies:
        print("[STOP] no proxies")
        return

    async with async_playwright() as p:
        for idx, proxy in enumerate(proxies, start=1):
            ok = await try_proxy(p, proxy, idx, len(proxies))
            if ok:
                print(f"\n[WINNER] {proxy}")
                return

    print("\n[FINAL] no working proxy found")


asyncio.run(main())