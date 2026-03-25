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
        "socket_timeout": 10,
        "outtmpl": "/tmp/%(title)s.%(ext)s",
        "retries": 2,
        "nocheckcertificate": True,
        "geo_bypass": True,
    }


def _etype(e):
    s = str(e).lower()
    if "timeout" in s:
        return "TIMEOUT"
    if "proxy" in s:
        return "PROXY"
    if "network" in s:
        return "NETWORK"
    return "YOUTUBE"


def download_video(url, mode, user):
    proxies = get() or [None]

    for i, p in enumerate(proxies[:MAX], 1):
        for fmt in _formats(mode):
            try:
                log.try_p(user, i, MAX, p)

                t0 = time.time()

                with yt_dlp.YoutubeDL(_opts(p, fmt)) as ydl:
                    info = ydl.extract_info(url, download=True)

                path = ydl.prepare_filename(info)

                dt = time.time() - t0
                size = round(info.get("filesize", 0) / (1024 * 1024), 2)

                if p:
                    mark_ok(p)
                    log.proxy_used(user, p)

                log.success(user, p, size, dt)

                return path, info

            except Exception as e:
                err = str(e)
                et = _etype(e)

                if p:
                    mark_fail(p)
                    ban(p, err)

                log.error(user, p, et, err)

    raise Exception("All attempts failed")
