# === handlers.py ===
# BUILD: 20260408-01-SMULE-SINGLE-BROWSER-SINGLE-DOWNLOAD

from datetime import datetime, timezone
import asyncio
import contextlib
import os
from logger import log_mem
from aiogram import types, Dispatcher
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import (
    STAGE_MODE,
    ALLOWED_USER_IDS,
    BOT_CODE,
    TOKEN,
    ALERT_CHANNEL_ID,
    PROCESSING_WAIT_TIMEOUT_SEC,
    PROCESSING_POLL_INTERVAL_SEC,
    FLOW_TIMEOUT_SEC,
    MEM_LOG_INTERVAL_SEC,
)
from bot_core.utils import log
from texts import TEXTS
from bot_core.alerts import send_alert, build_download_fail_alert
from bot_core.events import insert_bot_entry
from bot_core.user_settings import set_user_lang
from bot_i18n import t, user_lang
from smule_extract_browser_session import (
    extract_smule,
    download_smule_file_in_browser,
    close_smule_browser_extract,
)
from smule_flow import (
    parse_smule_url,
    insert_event_safe,
    build_extract_fail_text,
)
from smule_download import (
    pick_smule_media,
    build_smule_title,
    build_final_path,
)

def get_message_age_sec(message: types.Message) -> float:
    now = datetime.now(timezone.utc)
    msg_time = message.date if message.date else now
    return (now - msg_time).total_seconds()


async def mem_logger_task(message_id: int):
    try:
        while True:
            log_mem(f"bg message_id={message_id}")
            await asyncio.sleep(MEM_LOG_INTERVAL_SEC)
    except asyncio.CancelledError:
        pass

def lang_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺", callback_data="lang_ru"),
         InlineKeyboardButton(text="🇺🇸", callback_data="lang_en")]
    ])


def register_handlers(dp: Dispatcher):

    @dp.message(Command("start"))
    async def start(message: types.Message):
        import bot_state
        bot_state.last_update_ts = datetime.now(timezone.utc).timestamp()
        log(f"[USER START] id={message.from_user.id}")

        try:
            insert_bot_entry(BOT_CODE, message.from_user.id)
            print(f"DB INSERT OK: bot_code={BOT_CODE}, user_id={message.from_user.id}")
        except Exception as e:
            log(f"[DB INSERT ERROR] {e}")

        if STAGE_MODE and message.from_user.id not in ALLOWED_USER_IDS:
            await message.answer(
                TEXTS["stage_restricted"]["ru"] + " / " + TEXTS["stage_restricted"]["en"]
            )
            return

        await message.answer(
            TEXTS["choose_lang"]["ru"] + " / " + TEXTS["choose_lang"]["en"],
            reply_markup=lang_keyboard()
        )

    @dp.callback_query(lambda c: c.data.startswith("lang_"))
    async def set_lang(callback: types.CallbackQuery):
        lang = callback.data.split("_")[1]
        user_lang[callback.from_user.id] = lang

        try:
            set_user_lang(BOT_CODE, callback.from_user.id, lang)
            log(f"[DB LANG SAVE OK] bot_code={BOT_CODE} user_id={callback.from_user.id} lang={lang}")
        except Exception as e:
            log(f"[DB LANG SAVE ERROR] bot_code={BOT_CODE} user_id={callback.from_user.id} lang={lang} error={e}")

        await callback.message.edit_text(t("welcome", callback.from_user.id))

    @dp.message(lambda message: message.text and not message.text.startswith("/"))
    async def handle_video(message: types.Message):
        import bot_state
        
        log_mem("start_handle_video")
        user_id = message.from_user.id
        message_id = message.message_id
        dedupe_key = f"{message.chat.id}:{message.message_id}"
        bg_mem_task = asyncio.create_task(mem_logger_task(message_id))

        age_sec = get_message_age_sec(message)
        log(f"[FLOW AGE] message_id={message_id} age_sec={age_sec:.1f}")

        if age_sec > FLOW_TIMEOUT_SEC:
            log(f"[FLOW TIMEOUT] stage=entry message_id={message_id} age_sec={age_sec:.1f}")
            bg_mem_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await bg_mem_task
            return
        if STAGE_MODE and message.from_user.id not in ALLOWED_USER_IDS:
            await message.answer(
                TEXTS["stage_restricted"]["ru"] + " / " + TEXTS["stage_restricted"]["en"]
            )
            return

        if bot_state.user_requests.get(dedupe_key):
            log(f"[DEDUPE SKIP] key={dedupe_key} user_id={user_id}")
            return

        bot_state.user_requests[dedupe_key] = datetime.now(timezone.utc).timestamp()

        async with bot_state.download_semaphore:
            log_mem("before_download")
            url = parse_smule_url(message.text)
            age_sec = get_message_age_sec(message)
            log(f"[FLOW AGE] stage=before_download message_id={message_id} age_sec={age_sec:.1f}")

            if age_sec > FLOW_TIMEOUT_SEC:
                log(f"[FLOW TIMEOUT] stage=before_download message_id={message_id} age_sec={age_sec:.1f}")
                return
            if not url:
                insert_event_safe(
                    BOT_CODE,
                    user_id,
                    "url_received_invalid",
                    status="fail"
                )
                await message.answer(t("invalid_url", user_id))
                bot_state.user_requests.pop(dedupe_key, None)
                return

            insert_event_safe(
                BOT_CODE,
                user_id,
                "url_received",
                status="success"
            )
            await message.answer(t("start", user_id))

            now = datetime.now(timezone.utc)
            msg_time = message.date if message.date else now
            lag_sec = (now - msg_time).total_seconds()

            if lag_sec > 10:
                await message.answer(t("lag_long", user_id))

            log(f"[SMULE PW CALL] url={url}")

            file_path = None
            extract = None
            mode = None
            media_url = None

            try:
                insert_event_safe(
                    BOT_CODE,
                    user_id,
                    "download_started",
                    status="success"
                )

                extract = await extract_smule(url, keep_browser_open=True)
                log_mem("after_extract")

                if not extract or not extract.get("ok"):
                    insert_event_safe(
                        BOT_CODE,
                        user_id,
                        "extract_failed",
                        status="fail",
                        error_text_short=(extract.get("reason") if extract else "no_extract")[:500]
                    )
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
                    return

                log(
                    f"[SMULE EXTRACT RESULT] user_id={user_id} message_id={message_id} url={url} "
                    f"ok={extract.get('ok')} "
                    f"proxy={extract.get('proxy')} "
                    f"perf_found={bool(extract.get('perf'))} "
                    f"media_count={len(extract.get('media', []))}"
                )

                perf = extract.get("perf") or {}
                perf_type = perf.get("perf_type")
                perf_status = perf.get("perf_status")

                if perf_status == "processing":
                    await close_smule_browser_extract(extract)
                    extract = None

                    start = datetime.now(timezone.utc)

                    while True:
                        await asyncio.sleep(PROCESSING_POLL_INTERVAL_SEC)

                        try:
                            retry_extract = await extract_smule(url)
                        except Exception as e:
                            log(f"[SMULE RETRY EXTRACT ERROR] user_id={user_id} message_id={message_id} error={e}")
                            continue

                        if not retry_extract or not retry_extract.get("ok"):
                            log(f"[SMULE RETRY EXTRACT NOT READY] user_id={user_id} message_id={message_id}")
                            continue

                        retry_perf = retry_extract.get("perf") or {}
                        if not retry_perf:
                            log(f"[SMULE RETRY PERF MISSING] user_id={user_id} message_id={message_id}")
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
                            await message.answer(t("smule_media_not_ready", user_id))
                            return

                    extract = await extract_smule(url, keep_browser_open=True)
                    if not extract or not extract.get("ok"):
                        raise RuntimeError(
                            f"Browser extract failed: {extract.get('reason') if extract else 'no_extract'}"
                        )

                    perf = extract.get("perf") or {}
                    perf_type = perf.get("perf_type")
                    perf_status = perf.get("perf_status")

                mode, media_url = pick_smule_media(extract)

                if not mode or not media_url:
                    insert_event_safe(
                        BOT_CODE,
                        user_id,
                        "media_url_not_found",
                        status="fail",
                        error_text_short=f"perf_type={perf_type}; perf_status={perf_status}"[:500]
                    )
                    await message.answer(t("error", user_id))
                    return

                insert_event_safe(
                    BOT_CODE,
                    user_id,
                    "extract_success",
                    status="success"
                )

                await message.answer(t("status_preparing", user_id))

                if mode == "audio":
                    await message.answer(t("status_audio", user_id))
                else:
                    await message.answer(t("status_video", user_id))

                temp_path = await download_smule_file_in_browser(
                    extract,
                    media_url,
                    mode
                )
                log_mem("after_download")
                title = build_smule_title(extract)
                file_path = build_final_path(temp_path, title, mode)

                if not file_path or not os.path.exists(file_path):
                    raise RuntimeError("File not created")

                size = os.path.getsize(file_path)
                size_mb = round(size / (1024 * 1024), 2)

                result_text = t("file_info", user_id).format(
                    ext=("M4A" if mode == "audio" else "MP4"),
                    size=size_mb
                )

                final_caption = t("success", user_id) + "\n\n" + result_text

                if mode == "audio":
                    await message.answer_audio(
                        types.FSInputFile(file_path),
                        title=title,
                        performer=(extract.get("perf") or {}).get("artist") or "",
                        caption=final_caption
                    )
                else:
                    await message.answer_video(
                        types.FSInputFile(file_path),
                        caption=final_caption
                    )
                log_mem("after_send")
                insert_event_safe(
                    BOT_CODE,
                    user_id,
                    "download_success",
                    status="success",
                    mode=mode,
                    file_size_bytes=size
                )
                return

            except Exception as e:
                log(f"[SMULE DOWNLOAD ERROR] bot_code={BOT_CODE} user_id={user_id} message_id={message_id} mode={mode} error={e}")

                if "File too big" in str(e):
                    insert_event_safe(
                        BOT_CODE,
                        user_id,
                        "download_rejected_too_big",
                        status="rejected",
                        mode=mode
                    )
                    await message.answer(t("too_big", user_id))
                    return

                insert_event_safe(
                    BOT_CODE,
                    user_id,
                    "download_failed",
                    status="fail",
                    mode=mode,
                    error_text_short=str(e)[:500]
                )

                await message.answer(t("error", user_id))

                try:
                    alert_text = build_download_fail_alert(
                        BOT_CODE,
                        user_id,
                        url,
                        mode or "download",
                        str(e)
                    )
                    await send_alert(TOKEN, ALERT_CHANNEL_ID, alert_text)
                except Exception as alert_e:
                    log(f"[ALERT ERROR] bot_code={BOT_CODE} user_id={user_id} error={alert_e}")

                return

            finally:
                if extract:
                    await close_smule_browser_extract(extract)

                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        log(f"[CLEANUP ERROR] {e}")
                log_mem("finally_before_cleanup")
                bg_mem_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await bg_mem_task
                bot_state.user_requests.pop(dedupe_key, None)
