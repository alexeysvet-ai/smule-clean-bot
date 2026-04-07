# === handlers.py ===
# BUILD: 20260407-04-SMULE-BROWSER-DOWNLOAD-CLEAN

from datetime import datetime, timezone
import asyncio
import os

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

        user_id = message.from_user.id
        dedupe_key = f"{message.chat.id}:{message.message_id}"

        if dedupe_key in bot_state.user_requests:
            log(f"[DEDUPE SKIP] key={dedupe_key} user_id={user_id}")
            return

        bot_state.user_requests[dedupe_key] = datetime.now(timezone.utc).timestamp()

        try:
            if STAGE_MODE and message.from_user.id not in ALLOWED_USER_IDS:
                await message.answer(
                    TEXTS["stage_restricted"]["ru"] + " / " + TEXTS["stage_restricted"]["en"]
                )
                return

            url = parse_smule_url(message.text)

            if not url:
                insert_event_safe(
                    BOT_CODE,
                    user_id,
                    "url_received_invalid",
                    status="fail"
                )
                await message.answer(t("invalid_url", user_id))
                return

            insert_event_safe(
                BOT_CODE,
                user_id,
                "url_received",
                status="success"
            )

            now = datetime.now(timezone.utc)
            msg_time = message.date if message.date else now
            lag_sec = (now - msg_time).total_seconds()

            if lag_sec > 10:
                await message.answer(t("lag_long", user_id))

            log(f"[SMULE PW CALL] url={url}")

            try:
                extract = await extract_smule(url)
            except Exception as e:
                log(f"[SMULE EXTRACT EXCEPTION] user_id={user_id} url={url} error={e}")

                insert_event_safe(
                    BOT_CODE,
                    user_id,
                    "extract_exception",
                    status="fail",
                    error_text_short=str(e)[:500]
                )
                await message.answer(t("smule_extract_error", user_id))

                try:
                    alert_text = build_download_fail_alert(
                        BOT_CODE,
                        user_id,
                        url,
                        "extract",
                        str(e)
                    )
                    await send_alert(TOKEN, ALERT_CHANNEL_ID, alert_text)
                except Exception as alert_e:
                    log(f"[ALERT ERROR] bot_code={BOT_CODE} user_id={user_id} error={alert_e}")

                return

            log(
                f"[SMULE EXTRACT RESULT] user_id={user_id} url={url} "
                f"ok={extract.get('ok')} "
                f"proxy={extract.get('proxy')} "
                f"perf_found={bool(extract.get('perf'))} "
                f"media_count={len(extract.get('media', []))}"
            )

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

            perf = extract.get("perf") or {}
            perf_type = perf.get("perf_type")
            perf_status = perf.get("perf_status")

            if perf_status == "processing":
                start = datetime.now(timezone.utc)

                while True:
                    await asyncio.sleep(PROCESSING_POLL_INTERVAL_SEC)

                    try:
                        extract = await extract_smule(url)
                    except Exception as e:
                        log(f"[SMULE RETRY EXTRACT ERROR] user_id={user_id} error={e}")
                        continue

                    if not extract or not extract.get("ok"):
                        log(f"[SMULE RETRY EXTRACT NOT READY] user_id={user_id}")
                        continue

                    perf = extract.get("perf") or {}
                    if not perf:
                        log(f"[SMULE RETRY PERF MISSING] user_id={user_id}")
                        continue

                    perf_status = perf.get("perf_status")

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

            if mode == "audio":
                await message.answer(t("status_audio", user_id))
            else:
                await message.answer(t("status_video", user_id))

            file_path = None
            download_extract = None

            try:
                insert_event_safe(
                    BOT_CODE,
                    user_id,
                    "download_started",
                    status="success",
                    mode=mode
                )

                download_extract = await extract_smule(url, keep_browser_open=True)
                if not download_extract or not download_extract.get("ok"):
                    raise RuntimeError(
                        f"Browser extract failed: {download_extract.get('reason') if download_extract else 'no_extract'}"
                    )

                mode, media_url = pick_smule_media(download_extract)
                if not mode or not media_url:
                    raise RuntimeError("Browser media URL not found")

                temp_path = await download_smule_file_in_browser(
                    download_extract,
                    media_url,
                    mode
                )
                title = build_smule_title(download_extract)
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
                        performer=(download_extract.get("perf") or {}).get("artist") or "",
                        caption=final_caption
                    )
                else:
                    await message.answer_video(
                        types.FSInputFile(file_path),
                        caption=final_caption
                    )

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
                log(f"[SMULE DOWNLOAD ERROR] bot_code={BOT_CODE} user_id={user_id} mode={mode} error={e}")

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
                        mode,
                        str(e)
                    )
                    await send_alert(TOKEN, ALERT_CHANNEL_ID, alert_text)
                except Exception as alert_e:
                    log(f"[ALERT ERROR] bot_code={BOT_CODE} user_id={user_id} error={alert_e}")

                return

            finally:
                if download_extract:
                    await close_smule_browser_extract(download_extract)

                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        log(f"[CLEANUP ERROR] {e}")

        finally:
            bot_state.user_requests.pop(dedupe_key, None)
