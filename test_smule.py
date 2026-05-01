from playwright.sync_api import sync_playwright
from curl_cffi.requests import Session

print("START")

def test():
    print("TEST START")
    with sync_playwright() as p:
        print("PLAYWRIGHT OK")
        browser = p.chromium.launch(
            headless=True,
            proxy={"server": "http://gnktxrqy:munhcy6msboc@192.53.67.180:5729",
                   "username": "gnktxrqy",
                   "password": "munhcy6msboc"}
        )
        print("BROWSER OK")
        context = browser.new_context()
        page = context.new_page()
        
        url = "https://www.smule.com/sing-recording/2327427123_5203980702"
        page.goto(url, wait_until="domcontentloaded", timeout=10000)
        page.wait_for_timeout(3000)
        
        try:
            page.click("text=Accept Cookies", timeout=3000)
        except:
            pass
        
        page.wait_for_timeout(5000)
        
        perf = page.evaluate("""
            () => {
              const p = window?.DataStore?.Pages?.Recording?.performance || null;
              if (!p) return null;
              return { media_url: p.media_url, video_mp4: p.video_media_mp4_url }
            }
        """)
        print(f"perf={perf}")
        
        cookies_list = context.cookies()
        cookies = {c["name"]: c["value"] for c in cookies_list}
        print(f"cookie_names={list(cookies.keys())}")
        
        import base64
        SECRET_KEY = "TT18WlV5TXVeLXFXYn1WTF5qSmR9TXYpOHklYlFXWGY+SUZCRGNKPiU0emcyQ2l8dGVsamBkVlpA"

        def decode_smule_url(url_encoded):
            if not url_encoded or not url_encoded.startswith("e:"):
                return url_encoded
            def register_char_pool(value):
                return base64.b64decode(value + "=" * (-len(value) % 4)).decode("latin1")
            secret_pool = register_char_pool(SECRET_KEY)
            public_pool = register_char_pool(url_encoded[2:])
            state = list(range(256))
            h = 0
            for b in range(256):
                h = (h + state[b] + ord(secret_pool[b % len(secret_pool)])) % 256
                state[b], state[h] = state[h], state[b]
            out, b, h = [], 0, 0
            for ch in public_pool:
                b = (b + 1) % 256
                h = (h + state[b]) % 256
                state[b], state[h] = state[h], state[b]
                out.append(chr(ord(ch) ^ state[(state[b] + state[h]) % 256]))
            return "".join(out)

        media_url = decode_smule_url((perf or {}).get("media_url")) or decode_smule_url((perf or {}).get("video_mp4"))
        print(f"media_url={media_url}")
        
        if not media_url:
            print("NO MEDIA URL")
            browser.close()
            return
        
        with Session(impersonate="chrome120") as session:
            resp = session.get(
                media_url,
                headers={
                    "Referer": url,
                    "Origin": "https://www.smule.com",
                },
                cookies=cookies,
                proxies={"https": "http://gnktxrqy:munhcy6msboc@192.53.67.180:5729"},
            )
            print(f"status={resp.status_code}")
        
        browser.close()

test()
print("END")