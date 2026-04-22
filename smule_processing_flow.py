from datetime import datetime, timezone
import asyncio

from bot_core.utils import log
from config import (
    BOT_CODE,
    PROCESSING_WAIT_TIMEOUT_SEC,
    PROCESSING_POLL_INTERVAL_SEC,
)
from bot_i18n import t
from smule_extract_browser_session import (
    extract_smule,
    close_smule_browser_extract,
)
from smule_flow import insert_event_safe


async def resolve_processing_extract(
    *,
    extract: dict,
    url: str,
    user_id: int,
    message_target,
    log_suffix: str = "",
) -> dict | None:
    perf = extract.get("perf") or {}
    perf_status = perf.get("perf_status")

    if perf_status != "processing":
        return extract

    await close_smule_browser_extract(extract)

    start = datetime.now(timezone.utc)

    while True:
        await asyncio.sleep(PROCESSING_POLL_INTERVAL_SEC)

        try:
            retry_extract = await extract_smule(url)
        except Exception as e:
            log(f"[SMULE RETRY EXTRACT ERROR] user_id={user_id}{log_suffix} error={e}")
            continue

        if not retry_extract or not retry_extract.get("ok"):
            log(f"[SMULE RETRY EXTRACT NOT READY] user_id={user_id}{log_suffix}")
            continue

        retry_perf = retry_extract.get("perf") or {}
        if not retry_perf:
            log(f"[SMULE RETRY PERF MISSING] user_id={user_id}{log_suffix}")
            continue

        perf_status = retry_perf.get("perf_status")

        if perf_status != "processing":
            break

        if (datetime.now(timezone.utc) - start).total_seconds() > PROCESSING_WAIT_TIMEOUT_SEC:
            insert_event_safe(
                BOT_CODE,
                user_id,
                "media_not_ready_timeout",
                status="fail"
            )
            await message_target.answer(t("smule_media_not_ready", user_id))
            return None

    extract = await extract_smule(url, keep_browser_open=True)
    if not extract or not extract.get("ok"):
        raise RuntimeError(
            f"Browser extract failed: {extract.get('reason') if extract else 'no_extract'}"
        )

    return extract