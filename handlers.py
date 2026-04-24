# === handlers.py ===
# BUILD: 20260408-01-SMULE-SINGLE-BROWSER-SINGLE-DOWNLOAD

from datetime import datetime, timezone
from types import SimpleNamespace

from aiogram import types, Dispatcher
from aiogram.filters import Command

from config import (
    STAGE_MODE,
    ALLOWED_USER_IDS,
    BOT_CODE,
    TOKEN,
    ALERT_CHANNEL_ID,
    FLOW_TIMEOUT_SEC,
)
from bot_core.utils import log
from texts import TEXTS
from bot_core.alerts import send_alert, build_download_fail_alert
from bot_core.events import insert_bot_entry
from bot_core.user_settings import set_user_lang
from bot_i18n import t, user_lang
from smule_handler_helpers import ensure_smule_pending
from smule_extract_browser_session import (
    extract_smule,
    download_smule_file_in_browser,
    close_smule_browser_extract,
)
from smule_flow import (
    parse_smule_url,
    insert_event_safe,
)
from smule_media_flow import (
    resolve_available_media,
    has_any_media,
    handle_no_media,
    handle_audio_download,
    handle_video_download,
)
from smule_ui import (
    get_message_age_sec,
    lang_keyboard,
    format_keyboard,
)
from smule_handler_helpers import (
    send_extract_fail_and_alert,
    cleanup_extract_and_file,
)
from smule_processing_flow import resolve_processing_extract
from smule_mode_dispatch import run_smule_download_by_mode

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
    @dp.callback_query(lambda c: c.data in ("smule_format_audio", "smule_format_video"))
    async def choose_smule_format(callback: types.CallbackQuery):
        import bot_state

        user_id = callback.from_user.id

        ensure_smule_pending(bot_state)

        pending = bot_state.smule_pending.get(user_id)
        if not pending:
            await callback.answer("Request expired", show_alert=False)
            await callback.message.answer(t("expired_request", user_id))
            return

        url = pending.get("url")
        chat_id = pending.get("chat_id")
        format_message_id = pending.get("format_message_id")
        mode = "audio" if callback.data == "smule_format_audio" else "video"

        await callback.answer()

        now = datetime.now(timezone.utc)
        msg_time = callback.message.date if callback.message else now
        lag_sec = (now - msg_time).total_seconds()

        if lag_sec > 10:
            await callback.message.answer(t("lag_long", user_id))

        if chat_id and format_message_id:
            await callback.bot.edit_message_text(
                chat_id=chat_id,
                message_id=format_message_id,
                text=t("status_preparing", user_id)
            )
        else:
            await callback.message.answer(t("status_preparing", user_id))

        file_path = None
        extract = None

        try:
            insert_event_safe(
                BOT_CODE,
                user_id,
                "download_started",
                status="success"
            )

            extract = await extract_smule(url, keep_browser_open=True)

            if not extract or not extract.get("ok"):
                raise RuntimeError(
                    f"Browser extract failed: {extract.get('reason') if extract else 'no_extract'}"
                )

            extract = await resolve_processing_extract(
                extract=extract,
                url=url,
                user_id=user_id,
                message_target=callback.message,
            )
            if extract is None:
                return

            media_info = resolve_available_media(extract)

            if (
               (mode == "audio" and not media_info["has_audio"])
               or (mode == "video" and not media_info["has_video"])
               ):
                await handle_no_media(
                    user_id=user_id,
                    url=url,
                    message_target=callback.message,
                )
                return

            file_path, _ = await run_smule_download_by_mode(
                mode=mode,
                message_target=callback.message,
                callback_for_send=callback,
                user_id=user_id,
                url=url,
                extract=extract,
                download_func=download_smule_file_in_browser,
                handle_audio_download=handle_audio_download,
                handle_video_download=handle_video_download,
            )

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
                await callback.message.answer(t("too_big", user_id))
                return

            insert_event_safe(
                BOT_CODE,
                user_id,
                "download_failed",
                status="fail",
                mode=mode,
                error_text_short=str(e)[:500]
            )

            await callback.message.answer(t("error", user_id))

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

        finally:
            bot_state.smule_pending.pop(user_id, None)
            await cleanup_extract_and_file(
                extract,
                file_path,
                close_smule_browser_extract,
            )
    @dp.message(lambda message: message.text and not message.text.startswith("/"))
    async def handle_video(message: types.Message):
        import bot_state
        
        user_id = message.from_user.id
        message_id = message.message_id
        dedupe_key = f"{message.chat.id}:{message.message_id}"

        age_sec = get_message_age_sec(message)
        log(f"[FLOW AGE] message_id={message_id} age_sec={age_sec:.1f}")

        if age_sec > FLOW_TIMEOUT_SEC:
            log(f"[FLOW TIMEOUT] stage=entry message_id={message_id} age_sec={age_sec:.1f}")

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
                extract = await extract_smule(url, keep_browser_open=True)

                if not extract or not extract.get("ok"):
                    await send_extract_fail_and_alert(
                        user_id=user_id,
                        url=url,
                        extract=extract,
                        message=message,
                    )
                    return

                perf = extract.get("perf") or {}
                log(
                    f"[SMULE EXTRACT RESULT] user_id={user_id} message_id={message_id} url={url} "
                    f"ok={extract.get('ok')} "
                    f"proxy={extract.get('proxy')} "
                    f"perf_found={bool(perf)} "
                    f"perf_type={perf.get('perf_type')} "
                    f"perf_status={perf.get('perf_status')} "
                    f"media_count={len(extract.get('media', []))}"
                )

                extract = await resolve_processing_extract(
                    extract=extract,
                    url=url,
                    user_id=user_id,
                    message_target=message,
                    log_suffix=f" message_id={message_id}",
                )
                if extract is None:
                    return

                perf = extract.get("perf") or {}
                perf_type = perf.get("perf_type")

                if not hasattr(bot_state, "smule_pending"):
                    bot_state.smule_pending = {}

                insert_event_safe(
                    BOT_CODE,
                    user_id,
                    "extract_success",
                    status="success"
                )

                media_info = resolve_available_media(extract)
                perf_type = (extract.get("perf") or {}).get("perf_type")

                if not has_any_media(extract):
                    await handle_no_media(
                        user_id=user_id,
                        url=url,
                        message_target=message,
                    )
                    return

                if perf_type == "audio" and media_info["has_audio"]:
                    file_path, _ = await run_smule_download_by_mode(
                        mode="audio",
                        message_target=message,
                        callback_for_send=SimpleNamespace(message=message),
                        user_id=user_id,
                        url=url,
                        extract=extract,
                        download_func=download_smule_file_in_browser,
                        handle_audio_download=handle_audio_download,
                        handle_video_download=handle_video_download,
                    )
                    return

                format_msg = await message.answer(
                    t("choose_format", user_id),
                    reply_markup=format_keyboard(user_id)
                )

                bot_state.smule_pending[user_id] = {
                    "url": url,
                    "chat_id": format_msg.chat.id,
                    "format_message_id": format_msg.message_id,
                }
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
                await cleanup_extract_and_file(
                    extract,
                    file_path,
                    close_smule_browser_extract,
                )
                bot_state.user_requests.pop(dedupe_key, None)
