"""Tiny Redis JSON cache with TTL. All keys live under aiauto:cache:*
so the updater's cache-clear step wipes them safely."""
from __future__ import annotations

import json
from typing import Any

from app.services.queue import CACHE_PREFIX
from app.services.redis_client import get_redis


async def cache_get(key: str) -> Any | None:
    try:
        raw = await get_redis().get(CACHE_PREFIX + key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


async def cache_set(key: str, value: Any, ttl_seconds: int = 30) -> None:
    try:
        await get_redis().set(CACHE_PREFIX + key, json.dumps(value, default=str),
                              ex=ttl_seconds)
    except Exception:
        pass  # cache is best-effort


async def cache_delete(key: str) -> None:
    try:
        await get_redis().delete(CACHE_PREFIX + key)
    except Exception:
        pass
