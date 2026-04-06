import requests
from urllib.parse import urlparse
from bot_core.utils import log


def inspect_smule_url(url: str) -> dict:
    result = {
        "ok": False,
        "reason": "",
        "is_video": None,
    }

    try:
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()
        path = parsed.path or ""

        log(f"[SMULE CHECK START] url={url}")

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

        response = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
            },
            timeout=15,
            allow_redirects=True,
        )

        final_url = response.url
        final_host = (urlparse(final_url).netloc or "").lower()
        body = response.text or ""
        body_l = body.lower()

        log(
            f"[SMULE CHECK HTTP] url={url} status={response.status_code} "
            f"final_url={final_url}"
        )

        if response.status_code != 200:
            result["reason"] = f"http_status:{response.status_code}"
            log(f"[SMULE CHECK FAIL] url={url} reason={result['reason']}")
            return result

        if not (final_host == "smule.com" or final_host.endswith(".smule.com")):
            result["reason"] = f"redirected_to_non_smule:{final_host}"
            log(f"[SMULE CHECK FAIL] url={url} reason={result['reason']}")
            return result

        if "<html" not in body_l and "<!doctype html" not in body_l:
            result["reason"] = "response_not_html"
            log(f"[SMULE CHECK FAIL] url={url} reason={result['reason']}")
            return result

        if (
            'property="og:video"' in body_l
            or "video/mp4" in body_l
            or '"video_url"' in body_l
            or '"has_video":true' in body_l
            or '"video":true' in body_l
        ):
            result["is_video"] = True
        elif (
            'property="og:audio"' in body_l
            or "audio/mpeg" in body_l
            or '"audio_url"' in body_l
            or '"has_video":false' in body_l
            or '"video":false' in body_l
        ):
            result["is_video"] = False

        result["ok"] = True
        result["reason"] = (
            f"http_status:200 final_host:{final_host} is_video:{result['is_video']}"
        )

        log(
            f"[SMULE CHECK OK] url={url} "
            f"is_video={result['is_video']} reason={result['reason']}"
        )
        return result

    except requests.exceptions.Timeout:
        result["reason"] = "timeout"
        log(f"[SMULE CHECK ERROR] url={url} error={result['reason']}")
        return result
    except Exception as e:
        result["reason"] = f"{type(e).__name__}: {e}"
        log(f"[SMULE CHECK ERROR] url={url} error={result['reason']}")
        return result