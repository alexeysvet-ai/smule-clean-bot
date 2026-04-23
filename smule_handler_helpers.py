import os

from bot_core.alerts import send_alert, build_download_fail_alert
from bot_core.utils import log
from config import BOT_CODE, TOKEN, ALERT_CHANNEL_ID
from smule_flow import insert_event_safe


def ensure_smule_pending(bot_state) -> None:
    if not hasattr(bot_state, "smule_pending"):
        bot_state.smule_pending = {}


async def send_extract_fail_and_alert(user_id: int, url: str, extract: dict | None, message) -> None:
    insert_event_safe(
        BOT_CODE,
        user_id,
        "extract_failed",
        status="fail",
        error_text_short=(extract.get("reason") if extract else "no_extract")[:500]
    )

    from smule_flow import build_extract_fail_text
    await message.answer(build_extract_fail_text(extract))

    try:
        alert_text = build_download_fail_alert(
            BOT_CODE,
            user_id,
            url,
            "extract",
            extract.get("reason") if extract else "no_extract"
        )
        await send_alert(TOKEN, ALERT_CHANNEL_ID, alert_text)
    except Exception as e:
        log(f"[ALERT ERROR] bot_code={BOT_CODE} user_id={user_id} error={e}")


async def cleanup_extract_and_file(extract, file_path: str | None, close_smule_browser_extract) -> None:
    if extract:
        await close_smule_browser_extract(extract)

    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            log(f"[CLEANUP ERROR] {e}")