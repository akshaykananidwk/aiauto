"""Redis-backed priority FIFO queue.

Jobs are members of a sorted set; the score encodes priority + arrival
order so that higher priority pops first and equal priorities pop FIFO:

    score = (10 - priority) * 1e12 + sequence_number

The worker consumes with BZPOPMIN (lowest score first).
"""
from __future__ import annotations

from app.services.redis_client import get_redis

QUEUE_KEY = "aiauto:queue:pending"
SEQ_KEY = "aiauto:queue:seq"
CANCEL_SET = "aiauto:queue:cancelled"
HEARTBEAT_KEY = "aiauto:worker:heartbeat"
CHROME_STATUS_KEY = "aiauto:worker:chrome"
CURRENT_JOB_KEY = "aiauto:worker:current_job"
CACHE_PREFIX = "aiauto:cache:"


def compute_score(priority: int, seq: int) -> float:
    priority = max(0, min(10, priority))
    return (10 - priority) * 1_000_000_000_000 + seq


class QueueService:
    def __init__(self) -> None:
        self.redis = get_redis()

    async def enqueue(self, prompt_id: str, priority: int = 0) -> int:
        seq = await self.redis.incr(SEQ_KEY)
        await self.redis.zadd(QUEUE_KEY, {prompt_id: compute_score(priority, seq)})
        return await self.size()

    async def size(self) -> int:
        return await self.redis.zcard(QUEUE_KEY)

    async def pending_ids(self, limit: int = 100) -> list[str]:
        return await self.redis.zrange(QUEUE_KEY, 0, limit - 1)

    async def position(self, prompt_id: str) -> int | None:
        rank = await self.redis.zrank(QUEUE_KEY, prompt_id)
        return None if rank is None else rank + 1

    async def remove(self, prompt_id: str) -> bool:
        removed = await self.redis.zrem(QUEUE_KEY, prompt_id)
        if not removed:
            # may already be picked up by the worker — flag for cancellation
            await self.redis.sadd(CANCEL_SET, prompt_id)
            await self.redis.expire(CANCEL_SET, 3600)
        return bool(removed)

    async def is_cancelled(self, prompt_id: str) -> bool:
        return bool(await self.redis.srem(CANCEL_SET, prompt_id))

    async def pop_blocking(self, timeout: int = 5) -> str | None:
        res = await self.redis.bzpopmin(QUEUE_KEY, timeout=timeout)
        return res[1] if res else None

    # ---- worker status ----
    async def worker_status(self) -> dict:
        try:
            heartbeat = await self.redis.get(HEARTBEAT_KEY)
            chrome = await self.redis.get(CHROME_STATUS_KEY)
            current_job = await self.redis.get(CURRENT_JOB_KEY)
        except Exception:  # Redis down — report offline instead of failing
            heartbeat = chrome = current_job = None
        return {
            "worker_online": heartbeat is not None,
            "chrome_connected": chrome == "connected",
            "playwright_ready": heartbeat is not None,
            "last_heartbeat": heartbeat,
            "current_job": current_job,
        }

    # ---- cache ----
    async def clear_cache(self) -> int:
        deleted = 0
        async for key in self.redis.scan_iter(f"{CACHE_PREFIX}*", count=500):
            await self.redis.delete(key)
            deleted += 1
        return deleted
