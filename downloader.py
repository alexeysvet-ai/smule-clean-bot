import time
import yt_dlp

from proxy import get, mark_ok, mark_fail, ban
from config import DOWNLOAD_TIMEOUT
import logger as log

MAX = 10

def _formats(mode):
    if mode == "audio":
        return ["bestaudio/best", "bestaudio"]
    return ["bestvideo+bestaudio/best", "best"]

def _opts(proxy, fmt):
    return {
        "format": fmt,
        "proxy": proxy,
        "quiet": True,
        "socket_timeout": DOWNLOAD_TIMEOUT,
        "outtmpl": "/tmp/%(title)s.%(ext)s",
        "retries": 2,
        "no_warnings": True
    }

def download_video(url, mode, proxy=None):
    # Инициализация параметров для yt_dlp
    fmt = _formats(mode)
    opts = _opts(proxy, fmt)
    ydl = yt_dlp.YoutubeDL(opts)

    log.start(url)  # Логирование начала запроса

    try:
        result = ydl.download([url])
        if result != 0:
            raise Exception("Failed to download video")
        mark_ok(proxy)
        log.success(url)  # Логирование успешной загрузки
    except Exception as e:
        mark_fail(proxy)
        log.error(url, str(e))  # Логирование ошибки
        raise e
