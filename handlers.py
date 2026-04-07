# === handlers.py (FULL FILE) ===
# BUILD: 20260407-02-SMULE-GUARDS

from datetime import datetime, timezone

from aiogram import types, Dispatcher
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import STAGE_MODE, ALLOWED_USER_IDS, BOT_CODE, TOKEN, ALERT_CHANNEL_ID
from bot_core.utils import log

from texts import TEXTS
from bot_core.alerts import send_alert, build_download_fail_alert
from bot_core.events import insert_bot_entry
from bot_core.user_settings import set_user_lang
from bot_i18n import t, user_lang
from smule_extract import extract_smule
from smule_flow import (
    parse_smule_url,
    insert_event_safe,
    build_extract_debug_text,
    build_extract_fail_text,
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
        user_id = message.from_user.id

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

        if not extract or not extract["ok"]:
            insert_event_safe(
                BOT_CODE,
                user_id,
                "extract_failed",
                status="fail",
                error_text_short=(extract.get('reason') if extract else 'no_extract')[:500]
            )

            await message.answer(build_extract_fail_text(extract))

            try:
                alert_text = build_download_fail_alert(
                    BOT_CODE,
                    user_id,
                    url,
                    "extract",
                    extract.get('reason') if extract else 'no_extract'
                )
                await send_alert(TOKEN, ALERT_CHANNEL_ID, alert_text)
            except Exception as e:
                log(f"[ALERT ERROR] bot_code={BOT_CODE} user_id={user_id} error={e}")

            return

        perf = extract.get("perf") or {}
        media = extract.get("media") or []
        perf_type = perf.get("perf_type")
        perf_status = perf.get("perf_status")
        is_video_like = perf_type in ("video", "visualizer")

        if perf_status == "processing":
            insert_event_safe(
                BOT_CODE,
                user_id,
                "media_not_ready",
                status="success",
                error_text_short=f"perf_type={perf_type}; perf_status={perf_status}"[:500]
            )

            await message.answer(t("smule_media_not_ready", user_id))
            return

        insert_event_safe(
            BOT_CODE,
            user_id,
            "extract_success",
            status="success"
        )
        await message.answer(build_extract_debug_text(extract))
        return