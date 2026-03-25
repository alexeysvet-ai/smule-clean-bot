# [BUILD 20260326-PROD-05] stable handlers without dp decorators

from aiogram import types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from downloader import download_video
import logger as log

req = {}

# --- keyboards ---
def format_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Аудио"), KeyboardButton(text="Видео")]
        ],
        resize_keyboard=True
    )


def register(dp):

    async def start(message: types.Message):
        await message.answer("Отправь ссылку на видео")

    async def handle_url(message: types.Message):
        if not message.text or "http" not in message.text:
            return

        user_id = message.from_user.id
        url = message.text.strip()

        req[user_id] = url

        log.info(f"[REQUEST] user={user_id} url={url}")

        await message.answer(
            "Выбери формат",
            reply_markup=format_kb()
        )

    async def handle_format(message: types.Message):
        if message.text not in ["Аудио", "Видео"]:
            return

        user_id = message.from_user.id

        if user_id not in req:
            await message.answer("Сначала пришли ссылку")
            return

        url = req[user_id]
        fmt = "audio" if message.text == "Аудио" else "video"

        log.info(f"[FORMAT] user={user_id} format={fmt}")

        await message.answer("Скачиваю...")

        try:
            await download_video(url, fmt, message)
            log.info(f"[SUCCESS] user={user_id}")
        except Exception as e:
            log.error(f"[ERROR] user={user_id} err={e}")
            await message.answer("Ошибка при скачивании")

    # 👇 РЕГИСТРАЦИЯ (v3-совместимая)
    dp.message.register(start, commands=["start"])
    dp.message.register(handle_url)
    dp.message.register(handle_format)
