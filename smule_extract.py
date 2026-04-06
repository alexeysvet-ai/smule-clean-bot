from playwright.sync_api import sync_playwright
from bot_core.utils import log


def extract_smule_media_info(url: str) -> dict:
    result = {
        "ok": False,
        "reason": "",
        "is_video": None,
        "is_processing": None,
        "audio_url": None,
        "video_url": None,
        "title": None,
        "artist": None,
        "perf_status": None,
        "perf_type": None,
    }

    try:
        log(f"[SMULE PW START] url={url}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            media_urls = set()

            def on_request(req):
                req_url = req.url
                if ".m4a" in req_url or ".mp4" in req_url or ".m3u8" in req_url:
                    media_urls.add(req_url)
                    log(f"[SMULE PW MEDIA] {req_url}")

            page.on("request", on_request)

            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)

            try:
                perf = page.evaluate("""
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
            except Exception as e:
                perf = None
                log(f"[SMULE PW PERF ERROR] {e}")

            log(f"[SMULE PW PERF FOUND] {bool(perf)}")

            # пробуем ткнуть play по центру
            try:
                page.mouse.click(320, 380)
                page.wait_for_timeout(5000)
            except Exception as e:
                log(f"[SMULE PW CLICK ERROR] {e}")

            urls = list(media_urls)

            if perf:
                result["title"] = perf.get("title")
                result["artist"] = perf.get("artist")
                result["perf_type"] = perf.get("perf_type")
                result["perf_status"] = perf.get("perf_status")

                if perf.get("video_media_url") or perf.get("video_media_mp4_url"):
                    result["is_video"] = True
                elif perf.get("perf_type") == "audio":
                    result["is_video"] = False

                if perf.get("perf_status") in ("n", "a"):
                    result["is_processing"] = False
                elif perf.get("perf_status") is None:
                    result["is_processing"] = None
                else:
                    result["is_processing"] = True

            result["audio_url"] = next((u for u in urls if ".m4a" in u), None)
            result["video_url"] = next((u for u in urls if ".mp4" in u or ".m3u8" in u), None)

            if result["video_url"] is not None:
                result["is_video"] = True
            elif result["audio_url"] is not None and result["is_video"] is None:
                result["is_video"] = False

            result["ok"] = bool(perf or result["audio_url"] or result["video_url"])
            result["reason"] = (
                f"playwright_extract "
                f"perf_found:{bool(perf)} "
                f"audio:{bool(result['audio_url'])} "
                f"video:{bool(result['video_url'])} "
                f"status:{result['perf_status']}"
            )

            browser.close()

        log(f"[SMULE PW RESULT] {result}")
        return result

    except Exception as e:
        result["reason"] = f"{type(e).__name__}: {e}"
        log(f"[SMULE PW ERROR] {result['reason']}")
        return result