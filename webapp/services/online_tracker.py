import time
import asyncio
import logging

logger = logging.getLogger(__name__)

ONLINE_TTL = 300  # 5 minutes
CLEANUP_INTERVAL = 120  # run cleanup every 2 minutes

_active_users: dict[str, dict] = {}  # user_id -> {username, last_seen}


def ping(user_id: str, username: str):
    now = time.time()
    existing = _active_users.get(user_id)
    if existing:
        existing["last_seen"] = now
        if username:
            existing["username"] = username
    else:
        _active_users[user_id] = {"username": username or "", "last_seen": now}


def get_online_users() -> list[dict]:
    now = time.time()
    return [
        {"user_id": uid, "username": info["username"], "last_seen": info["last_seen"]}
        for uid, info in _active_users.items()
        if now - info["last_seen"] <= ONLINE_TTL
    ]


def get_online_count() -> int:
    now = time.time()
    return sum(
        1 for info in _active_users.values()
        if now - info["last_seen"] <= ONLINE_TTL
    )


def _cleanup():
    now = time.time()
    stale = [
        uid for uid, info in _active_users.items()
        if now - info["last_seen"] > ONLINE_TTL
    ]
    for uid in stale:
        del _active_users[uid]
    if stale:
        logger.debug("Online tracker: removed %d stale users", len(stale))


async def cleanup_loop():
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL)
        _cleanup()
