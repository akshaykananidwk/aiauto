from __future__ import annotations

import redis.asyncio as aioredis

from app.core.config import get_settings

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(
            get_settings().redis_url,
            decode_responses=True,
            # RESP2: newer redis-py defaults to the RESP3 HELLO handshake,
            # which Redis servers older than 6.0 (e.g. the Windows 5.0 port)
            # reject with "unknown command HELLO"
            protocol=2,
            # fail fast when Redis is down instead of stalling API requests
            # (socket_timeout must stay above the queue's 5s blocking pop)
            socket_connect_timeout=3,
            socket_timeout=10,
        )
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
