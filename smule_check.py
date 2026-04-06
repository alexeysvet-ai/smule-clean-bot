import requests
from urllib.parse import urlparse
from bot_core.utils import log


def inspect_smule_url(url: str) -> dict:
    result = {
        "ok": False,
        "reason": "",
        "is_video": None,
        "is_processing": None,
        "path_type": None,
        "http_status": None,
        "final_host": None,
        "content_type": None,
    }

    try:
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()
        path = parsed.path or ""
        query = parsed.query or ""

        log(f"[SMULE CHECK START] url={url}")
        log(f"[SMULE CHECK PARSED] scheme={parsed.scheme} host={host} path={path} query={query}")

        if not parsed.scheme or not host:
            result["reason"] = "url_parse_failed"
            log(f"[SMULE CHECK FAIL] url={url} reason={result['reason']}")
            return result

        if not (host == "smule.com" or host.endswith(".smule.com")):
            result["reason"] = f"not_smule_host:{host}"
            log(f"[SMULE CHECK FAIL] url={url} reason={result['reason']}")
            return result

        if not path or path == "/":
            result["reason"] = "empty_smule_path"
            log(f"[SMULE CHECK FAIL] url={url} reason={result['reason']}")
            return result

        # --- URL pattern detection first (P0-safe) ---
        path_l = path.lower()

        if "/sing-recording/" in path_l:
            result["path_type"] = "sing-recording"
            result["ok"] = True
        elif "/recording/" in path_l:
            result["path_type"] = "recording"
            result["ok"] = True
        else:
            result["reason"] = f"not_smule_recording_path:{path}"
            log(f"[SMULE CHECK FAIL] url={url} reason={result['reason']}")
            return result

        result["reason"] = f"matched_smule_{result['path_type']}_pattern"
        log(
            f"[SMULE CHECK PATTERN OK] url={url} "
            f"path_type={result['path_type']} reason={result['reason']}"
        )

        # --- HTTP diagnostics only: do not flip ok=False on 403/timeout ---
        try:
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

            response = requests.get(
                url,
                headers=headers,
                timeout=15,
                allow_redirects=True,
            )

            final_url = response.url
            final_host = (urlparse(final_url).netloc or "").lower()
            body = response.text or ""
            body_l = body.lower()
            content_type = response.headers.get("Content-Type", "")
            server = response.headers.get("Server", "")
            body_preview = body[:500].replace("\n", " ").replace("\r", " ")

            result["http_status"] = response.status_code
            result["final_host"] = final_host
            result["content_type"] = content_type

            log(
                f"[SMULE CHECK HTTP] url={url} status={response.status_code} "
                f"final_url={final_url} final_host={final_host} "
                f"content_type={content_type} server={server}"
            )
            log(f"[SMULE CHECK BODY PREVIEW] url={url} body_preview={body_preview}")

            # processing heuristics
            if (
                "processing" in body_l
                or "posting complete" in body_l
                or "still being processed" in body_l
                or "uploading" in body_l
                or "transcoding" in body_l
            ):
                result["is_processing"] = True
            else:
                result["is_processing"] = False

            # video/audio heuristics
            if (
                'property="og:video"' in body_l
                or "video/mp4" in body_l
                or '"video_url"' in body_l
                or '"has_video":true' in body_l
                or '"video":true' in body_l
                or '"camera":true' in body_l
            ):
                result["is_video"] = True
            elif (
                'property="og:audio"' in body_l
                or "audio/mpeg" in body_l
                or "audio/mp4" in body_l
                or '"audio_url"' in body_l
                or '"has_video":false' in body_l
                or '"video":false' in body_l
                or '"camera":false' in body_l
            ):
                result["is_video"] = False

            result["reason"] = (
                f"matched_smule_{result['path_type']}_pattern "
                f"http_status:{result['http_status']} "
                f"final_host:{result['final_host']} "
                f"content_type:{result['content_type']} "
                f"is_video:{result['is_video']} "
                f"is_processing:{result['is_processing']}"
            )

        except requests.exceptions.Timeout:
            result["reason"] = (
                f"matched_smule_{result['path_type']}_pattern "
                f"http_error:timeout "
                f"is_video:{result['is_video']} "
                f"is_processing:{result['is_processing']}"
            )
            log(f"[SMULE CHECK HTTP ERROR] url={url} error=timeout")
        except requests.exceptions.RequestException as e:
            result["reason"] = (
                f"matched_smule_{result['path_type']}_pattern "
                f"http_error:{type(e).__name__}:{e} "
                f"is_video:{result['is_video']} "
                f"is_processing:{result['is_processing']}"
            )
            log(f"[SMULE CHECK HTTP ERROR] url={url} error={type(e).__name__}: {e}")

        log(
            f"[SMULE CHECK OK] url={url} "
            f"path_type={result['path_type']} "
            f"http_status={result['http_status']} "
            f"is_video={result['is_video']} "
            f"is_processing={result['is_processing']} "
            f"reason={result['reason']}"
        )
        return result

    except Exception as e:
        result["reason"] = f"{type(e).__name__}: {e}"
        log(f"[SMULE CHECK ERROR] url={url} error={result['reason']}")
        return result