import json
import re
import requests
from urllib.parse import urlparse
from bot_core.utils import log
from proxy import get_active_proxies


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
        "cover_url": None,
        "author": None,
        "media_url": None,
        "video_media_url": None,
        "video_media_mp4_url": None,
        "perf_status": None,
        "perf_type": None,
        "private": None,
        "raw": None,
    }

    try:
        log(f"[SMULE EXTRACT START] url={url}")

        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()
        path = parsed.path or ""
        query = parsed.query or ""

        log(
            f"[SMULE EXTRACT PARSED] "
            f"scheme={parsed.scheme} host={host} path={path} query={query}"
        )

        if not parsed.scheme or not host:
            result["reason"] = "url_parse_failed"
            log(f"[SMULE EXTRACT FAIL] url={url} reason={result['reason']}")
            return result

        if not (host == "smule.com" or host.endswith(".smule.com")):
            result["reason"] = f"not_smule_host:{host}"
            log(f"[SMULE EXTRACT FAIL] url={url} reason={result['reason']}")
            return result

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.smule.com/",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }

        session = requests.Session()

        # первый прогрев (как браузер)
        session.get("https://www.smule.com/", headers=headers, timeout=10)
        
        proxies_list = get_active_proxies()
        log(f"[SMULE PROXIES] loaded={len(proxies_list)}")

        last_error = None
        response = None

        for idx, proxy in enumerate(proxies_list):
            try:
                log(f"[SMULE TRY {idx+1}/{len(proxies_list)}] proxy={proxy}")

                response = requests.get(
                    url,
                    headers=headers,
                    timeout=20,
                    allow_redirects=True,
                    proxies={
                        "http": proxy,
                        "https": proxy,
                    }
                )

                log(f"[SMULE PROXY SUCCESS] proxy={proxy} status={response.status_code}")
                break

            except Exception as e:
                last_error = str(e)
                log(f"[SMULE PROXY ERROR] proxy={proxy} error={last_error}")
                continue

        if response is None:
            log("[SMULE FALLBACK] trying without proxy")

            response = requests.get(
                url,
                headers=headers,
                timeout=20,
                allow_redirects=True,
            )

            log(f"[SMULE FALLBACK RESULT] status={response.status_code}")

        final_url = response.url
        final_host = (urlparse(final_url).netloc or "").lower()
        content_type = response.headers.get("Content-Type", "")
        body = response.text or ""
        body_preview = body[:500].replace("\n", " ").replace("\r", " ")
        with open("/tmp/smule_debug.html", "w", encoding="utf-8") as f:
            f.write(body)

        log("[SMULE EXTRACT DEBUG] saved_html=/tmp/smule_debug.html")
#        log(f"[SMULE EXTRACT DEBUG] body_first_500={body[:500]}")

        log(
            f"[SMULE EXTRACT HTTP] "
            f"url={url} status={response.status_code} "
            f"final_url={final_url} final_host={final_host} "
            f"content_type={content_type}"
        )
 #       log(f"[SMULE EXTRACT BODY PREVIEW] url={url} body_preview={body_preview}")

        if response.status_code not in (200, 403):
            result["reason"] = f"http_status:{response.status_code}"
            log(f"[SMULE EXTRACT FAIL] url={url} reason={result['reason']}")
            return result

        if response.status_code == 403:
            log(
                f"[SMULE EXTRACT INFO] url={url} "
                f"status=403 but trying to parse HTML anyway"
            )

        log(f"[SMULE EXTRACT BODY HAS WINDOW.DATASTORE] found={'window.DataStore' in body}")
        log(f"[SMULE EXTRACT COOKIES] {session.cookies.get_dict()}")
        log(f"[SMULE EXTRACT BODY HAS PERFORMANCE] found={'performance' in body}")
        log(f"[SMULE EXTRACT BODY HAS Pages] found={'Pages' in body}")
        log(f"[SMULE EXTRACT BODY LEN] len={len(body)}")

        datastore_match = re.search(
            r"window\.DataStore\s*=\s*(\{.*?\})\s*;",
            body,
            re.DOTALL,
        )

        if not datastore_match:
            log(f"[SMULE EXTRACT INFO] url={url} primary regex failed, trying fallback")

            datastore_match = re.search(
                r"window\.DataStore\s*=\s*(\{.*\})\s*;\s*",
                body,
                re.DOTALL,
            )

        if not datastore_match:
            result["reason"] = "datastore_not_found"
            log(f"[SMULE EXTRACT FAIL] url={url} reason={result['reason']}")
            log(f"[SMULE EXTRACT BODY PREVIEW 2000] {body[:2000]}")
            return result

        datastore_raw = datastore_match.group(1)
        log(
            f"[SMULE EXTRACT DATASTORE FOUND] "
            f"url={url} datastore_len={len(datastore_raw)}"
        )

        try:
            datastore = json.loads(datastore_raw)
        except Exception as e:
            result["reason"] = f"datastore_json_parse_failed:{type(e).__name__}:{e}"
            log(f"[SMULE EXTRACT FAIL] url={url} reason={result['reason']}")
            return result

        performance = (
            datastore.get("Pages", {})
            .get("Recording", {})
            .get("performance")
        )

        if not performance:
            result["reason"] = "performance_not_found"
            log(f"[SMULE EXTRACT FAIL] url={url} reason={result['reason']}")
            return result

        result["raw"] = performance
        result["perf_status"] = performance.get("perf_status")
        result["perf_type"] = performance.get("type")
        result["title"] = performance.get("title")
        result["artist"] = performance.get("artist")
        result["cover_url"] = performance.get("cover_url")
        result["media_url"] = performance.get("media_url")
        result["video_media_url"] = performance.get("video_media_url")
        result["video_media_mp4_url"] = performance.get("video_media_mp4_url")
        result["private"] = performance.get("private")

        owner = performance.get("owner") or {}
        result["author"] = owner.get("handle") or performance.get("performed_by")

        log(
            f"[SMULE EXTRACT PERFORMANCE] "
            f"title={result['title']} artist={result['artist']} "
            f"author={result['author']} perf_type={result['perf_type']} "
            f"perf_status={result['perf_status']} private={result['private']}"
        )

        log(
            f"[SMULE EXTRACT URLS] "
            f"media_url={'yes' if result['media_url'] else 'no'} "
            f"video_media_url={'yes' if result['video_media_url'] else 'no'} "
            f"video_media_mp4_url={'yes' if result['video_media_mp4_url'] else 'no'} "
            f"cover_url={'yes' if result['cover_url'] else 'no'}"
        )
        log(
            f"[SMULE EXTRACT RAW MEDIA] "
            f"media_url={result['media_url']} "
            f"video_media_url={result['video_media_url']} "
            f"video_media_mp4_url={result['video_media_mp4_url']}"
        )

        # --- is_video ---
        if result["video_media_url"] or result["video_media_mp4_url"]:
            result["is_video"] = True
        elif result["perf_type"] == "audio":
            result["is_video"] = False
        elif result["perf_type"] == "video":
            result["is_video"] = True

        # --- is_processing ---
        # пока простая эвристика
        if result["perf_status"] in ("n", "a"):
            result["is_processing"] = False
        elif result["perf_status"] is None:
            result["is_processing"] = None
        else:
            result["is_processing"] = True

        # --- direct urls ---
        # пока audio_url/video_url = только если уже прямые
        if isinstance(result["media_url"], str) and result["media_url"].startswith("http"):
            result["audio_url"] = result["media_url"]

        if isinstance(result["video_media_mp4_url"], str) and result["video_media_mp4_url"].startswith("http"):
            result["video_url"] = result["video_media_mp4_url"]
        elif isinstance(result["video_media_url"], str) and result["video_media_url"].startswith("http"):
            result["video_url"] = result["video_media_url"]

        result["ok"] = True
        result["reason"] = (
            f"extract_ok "
            f"perf_type:{result['perf_type']} "
            f"perf_status:{result['perf_status']} "
            f"is_video:{result['is_video']} "
            f"is_processing:{result['is_processing']} "
            f"has_media_url:{bool(result['media_url'])} "
            f"has_video_media_url:{bool(result['video_media_url'])} "
            f"has_video_media_mp4_url:{bool(result['video_media_mp4_url'])}"
        )

        log(
            f"[SMULE EXTRACT OK] "
            f"url={url} reason={result['reason']}"
        )

        return result

    except requests.exceptions.Timeout:
        result["reason"] = "timeout"
        log(f"[SMULE EXTRACT ERROR] url={url} error={result['reason']}")
        return result
    except requests.exceptions.RequestException as e:
        result["reason"] = f"request_exception:{type(e).__name__}:{e}"
        log(f"[SMULE EXTRACT ERROR] url={url} error={result['reason']}")
        return result
    except Exception as e:
        result["reason"] = f"{type(e).__name__}: {e}"
        log(f"[SMULE EXTRACT ERROR] url={url} error={result['reason']}")
        return result