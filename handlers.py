# === handlers.py (FULL FILE) ===
# BUILD: 20260407-01-SMULE-CLEANUP

from datetime import datetime, timezone
from bot_state import last_update_ts, process_start_ts
from aiogram import types, Dispatcher
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import STAGE_MODE, ALLOWED_USER_IDS, BOT_CODE, TOKEN, ALERT_CHANNEL_ID
from bot_core.utils import log
from texts import TEXTS
from bot_core.alerts import send_alert, build_download_fail_alert
from bot_core.events import insert_bot_entry, insert_bot_event
from bot_core.user_settings import set_user_lang
from bot_i18n import t, user_lang
from bot_core.bot_helpers import extract_url
from smule_extract import extract_smule


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

        raw_text = (message.text or "").strip()
        url = extract_url(raw_text)

        if not url:
            try:
                insert_bot_event(
                    BOT_CODE,
                    user_id,
                    "url_received_invalid",
                    status="fail"
                )
            except Exception as e:
                log(f"[DB EVENT ERROR] bot_code={BOT_CODE} user_id={user_id} event_type=url_received_invalid error={e}")

            await message.answer(t("invalid_url", user_id))
            return

        if "smule.com" not in url:
            try:
                insert_bot_event(
                    BOT_CODE,
                    user_id,
                    "url_received_invalid",
                    status="fail"
                )
            except Exception as e:
                log(f"[DB EVENT ERROR] bot_code={BOT_CODE} user_id={user_id} event_type=url_received_invalid error={e}")

            await message.answer(t("invalid_url", user_id))
            return

        try:
            insert_bot_event(
                BOT_CODE,
                user_id,
                "url_received",
                status="success"
            )
        except Exception as e:
            log(f"[DB EVENT ERROR] bot_code={BOT_CODE} user_id={user_id} event_type=url_received error={e}")

        now = datetime.now(timezone.utc)
        msg_time = message.date if message.date else now
        lag_sec = (now - msg_time).total_seconds()

        if lag_sec > 10:
            await message.answer(t("lag_long", user_id))

        log(f"[SMULE PW CALL] url={url}")
        extract = await extract_smule(url)
        log(
            f"[SMULE EXTRACT RESULT] user_id={user_id} url={url} "
            f"ok={extract.get('ok')} "
            f"proxy={extract.get('proxy')} "
            f"perf_found={bool(extract.get('perf'))} "
            f"media_count={len(extract.get('media', []))}"
        )

        if not extract or not extract["ok"]:
            try:
                insert_bot_event(
                    BOT_CODE,
                    user_id,
                    "extract_failed",
                    status="fail",
                    error_text_short=(extract.get('reason') if extract else 'no_extract')[:500]
                )
            except Exception as e:
                log(f"[DB EVENT ERROR] bot_code={BOT_CODE} user_id={user_id} event_type=extract_failed error={e}")

            await message.answer(
                f"EXTRACT FAIL\n"
                f"extract_reason={extract.get('reason') if extract else 'no_extract'}"
            )

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

        try:
            insert_bot_event(
                BOT_CODE,
                user_id,
                "extract_success",
                status="success"
            )
        except Exception as e:
            log(f"[DB EVENT ERROR] bot_code={BOT_CODE} user_id={user_id} event_type=extract_success error={e}")

        perf = extract.get("perf") or {}
        media = extract.get("media") or []

        await message.answer(
            f"OK\n"
            f"type={perf.get('perf_type')}\n"
            f"status={perf.get('perf_status')}\n"
            f"title={perf.get('title')}\n"
            f"media_count={len(media)}\n"
            f"proxy={extract.get('proxy')}"
        )
        return