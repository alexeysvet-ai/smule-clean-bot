import requests
import os

INPUT_FILE = "proxies.txt"
TEMP_FILE = "proxies.tmp"

MAX_GOOD_PROXIES = 5
TIMEOUT = 3


def is_proxy_alive(proxy):
    try:
        proxies = {
            "http": proxy,
            "https": proxy,
        }

        r = requests.get(
            "https://www.youtube.com/generate_204",
            proxies=proxies,
            timeout=TIMEOUT
        )

        return r.status_code in (200, 204)

    except Exception:
        return False


def load_proxies():
    with open(INPUT_FILE, "r") as f:
        return [line.strip() for line in f if line.strip()]


def save_proxies(proxies):
    with open(TEMP_FILE, "w") as f:
        for p in proxies:
            f.write(p + "\n")

    os.replace(TEMP_FILE, INPUT_FILE)


def run_proxy_refresh():
    proxies = load_proxies()
    alive = []

    print(f"[CRON] total={len(proxies)}")

    for idx, proxy in enumerate(proxies, start=1):
        print(f"[CRON CHECK {idx}/{len(proxies)}] {proxy}")

        if is_proxy_alive(proxy):
            print(f"[CRON OK] {proxy}")
            alive.append(proxy)

        if len(alive) >= MAX_GOOD_PROXIES:
            break

    print(f"[CRON RESULT] alive={len(alive)}")

    if alive:
        save_proxies(alive)
        print("[CRON SAVED]")
    else:
        print("[CRON SKIP]")
