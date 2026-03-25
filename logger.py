import time

BUILD = time.strftime("%Y%m%d-%H%M")
print(f"[BUILD] {BUILD} started")


def _ts():
    return time.strftime("%H:%M:%S")


def log(msg):
    print(f"[{_ts()}] [{BUILD}] {msg}")


def request(u, url):
    log(f"[REQUEST] user={u} url={url}")


def start(u, mode, url):
    log(f"[DOWNLOAD START] user={u} mode={mode} url={url}")


def try_p(u, i, total, p):
    log(f"[TRY] user={u} attempt={i}/{total} proxy={p}")


def proxy_used(u, p):
    log(f"[PROXY USED] user={u} proxy={p}")


def success(u, p, size, t):
    log(f"[SUCCESS] user={u} proxy={p} size={size}MB time={t:.1f}s")


def error(u, p, et, e):
    log(f"[ERROR] user={u} proxy={p} type={et} error={e}")


def final_error(u, url, r):
    log(f"[FINAL ERROR] user={u} url={url} reason={r}")


def file(u, ext, size, abr=None):
    msg = f"[FILE] user={u} ext={ext} size={size}MB"
    if abr:
        msg += f" bitrate={abr}"
    log(msg)


def time_log(u, t):
    log(f"[TIME] user={u} total={t:.1f}s")


def cleanup(u):
    log(f"[CLEANUP] user={u} file_deleted")
