# === smule_flow.py ===
# BUILD: 20260407-01-SMULE-FLOW-BASE

from bot_core.utils import log
from bot_core.events import insert_bot_event
from bot_core.bot_helpers import extract_url


def parse_smule_url(raw_text: str | None) -> str | None:
    raw_text = (raw_text or "").strip()
    url = extract_url(raw_text)
    if not url:
        return None
    if "smule.com" not in url:
        return None
    return url


def insert_event_safe(bot_code: str, user_id: int, event_type: str, **kwargs):
    try:
        insert_bot_event(bot_code, user_id, event_type, **kwargs)
    except Exception as e:
        log(
            f"[DB EVENT ERROR] bot_code={bot_code} "
            f"user_id={user_id} event_type={event_type} error={e}"
        )


def build_extract_debug_text(extract: dict) -> str:
    perf = extract.get("perf") or {}
    media = extract.get("media") or []

    return (
        f"OK\n"
        f"type={perf.get('perf_type')}\n"
        f"status={perf.get('perf_status')}\n"
        f"title={perf.get('title')}\n"
        f"media_count={len(media)}\n"
        f"proxy={extract.get('proxy')}"
    )


def build_extract_fail_text(extract: dict | None) -> str:
    reason = extract.get("reason") if extract else "no_extract"
    return (
        f"EXTRACT FAIL\n"
        f"extract_reason={reason}"
    )