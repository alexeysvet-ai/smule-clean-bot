import time

PROXIES = []

state = {}
blacklist = {}

SHORT, MEDIUM, LONG = 10, 60, 300


def score(p):
    s = state.get(p, {"s": 0, "f": 0})
    return s["s"] - s["f"]


def sorted_proxies():
    return sorted(PROXIES, key=score, reverse=True)


def is_bad(p):
    return p in blacklist and time.time() < blacklist[p]


def mark_ok(p):
    s = state.setdefault(p, {"s": 0, "f": 0})
    s["s"] += 1


def mark_fail(p):
    s = state.setdefault(p, {"s": 0, "f": 0})
    s["f"] += 1


def ban(p, err):
    ttl = SHORT
    if "403" in err:
        ttl = MEDIUM
    if "sign" in err:
        ttl = LONG
    blacklist[p] = time.time() + ttl


def get():
    return [p for p in sorted_proxies() if not is_bad(p)]
