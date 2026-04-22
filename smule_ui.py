from datetime import datetime, timezone

from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot_i18n import t


def get_message_age_sec(message: types.Message) -> float:
    now = datetime.now(timezone.utc)
    msg_time = message.date if message.date else now
    return (now - msg_time).total_seconds()


def lang_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺", callback_data="lang_ru"),
         InlineKeyboardButton(text="🇺🇸", callback_data="lang_en")]
    ])


def format_keyboard(user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t("format_audio", user_id), callback_data="smule_format_audio"),
            InlineKeyboardButton(text=t("format_video", user_id), callback_data="smule_format_video"),
        ]
    ])