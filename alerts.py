from aiogram import Bot
from datetime import datetime, timezone
from config import STAGE_MODE
from utils import log

def build_download_fail_alert(bot_code: str, user_id: int, url: str, mode: str, err: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    err1 = str(err).replace("ERROR: ", "").replace("Error: ","")

    return (
        f"🚨 Download failed\n"
        f"bot: {bot_code}\n"
        f"time: {now}\n"
        f"user_id: {user_id}\n"
        f"mode: {mode}\n"
        f"url: {url}\n"
        f"error: {err1}"
    )

async def send_alert(token: str, chat_id: int | str, text: str):
    log(f"[ALERT DEBUG] chat_id={chat_id}")
    log(f"[ALERT DEBUG] token={token[:10]}")
    async with Bot(token=token) as bot_alert:
        await bot_alert.send_message(chat_id=chat_id, text=text)