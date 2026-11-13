"""Sliding window rate limiting on Valkey (S-12)."""

from __future__ import annotations

import time
from functools import lru_cache

from redis.asyncio import Redis

from arha.core.errors import AppError
from arha.core.ids import uuid7
from arha.settings import get_settings


@lru_cache
def valkey() -> Redis:
    return Redis.from_url(get_settings().valkey_url, decode_responses=True)


class RateLimited(AppError):
    def __init__(self, retry_after: int) -> None:
        super().__init__("rate_limited", 429, extra={"retry_after": retry_after})


async def hit(bucket: str, limit: int, window_seconds: int) -> None:
    """Raise RateLimited when more than `limit` hits happened in the last `window_seconds`."""
    key = f"rl:{bucket}"
    now = time.time()
    pipe = valkey().pipeline()
    pipe.zremrangebyscore(key, 0, now - window_seconds)
    pipe.zadd(key, {uuid7().hex: now})
    pipe.zcard(key)
    pipe.expire(key, window_seconds)
    _, _, count, _ = await pipe.execute()
    if int(count) > limit:
        raise RateLimited(window_seconds)


LIMITS = {
    "login": (5, 60),
    "submission": (20, 60),
    "api": (600, 60),
    "resume": (5, 3600),
    "signup": (10, 3600),
    "report": (5, 3600),
    "payment_status": (60, 60),
}


async def limit(name: str, *parts: str) -> None:
    count, window = LIMITS[name]
    await hit(":".join((name, *parts)), count, window)
