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
WORKERS_PREFIX = "aiauto:worker:info:"  # one hash per worker, TTL-expired
WORKER_TTL_SECONDS = 20
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

    async def in_queue(self, prompt_id: str) -> bool:
        """Exact membership check — unlike pending_ids this is not capped."""
        return await self.redis.zscore(QUEUE_KEY, prompt_id) is not None

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
        """Consume the cancel flag (destructive — use once per job start)."""
        return bool(await self.redis.srem(CANCEL_SET, prompt_id))

    async def peek_cancelled(self, prompt_id: str) -> bool:
        """Non-destructive cancel-flag check (safe to poll mid-job)."""
        return bool(await self.redis.sismember(CANCEL_SET, prompt_id))

    async def clear_cancel_flag(self, prompt_id: str) -> None:
        """Remove a stale cancel flag (must happen before re-enqueueing a
        previously-cancelled prompt, or the worker cancels it instantly)."""
        await self.redis.srem(CANCEL_SET, prompt_id)

    async def pop_blocking(self, timeout: int = 5) -> str | None:
        res = await self.redis.bzpopmin(QUEUE_KEY, timeout=timeout)
        return res[1] if res else None

    # ---- worker registry (supports multiple workers) ----
    async def register_heartbeat(
        self, worker_id: str, *, chrome: str, current_job: str | None
    ) -> None:
        key = WORKERS_PREFIX + worker_id
        from datetime import datetime, timezone

        await self.redis.hset(key, mapping={
            "heartbeat": datetime.now(timezone.utc).isoformat(),
            "chrome": chrome,
            "current_job": current_job or "",
        })
        await self.redis.expire(key, WORKER_TTL_SECONDS)

    async def deregister_worker(self, worker_id: str) -> None:
        """Remove a worker's heartbeat immediately on clean shutdown so a
        supervisor restart isn't blocked by the dead predecessor's TTL."""
        await self.redis.delete(WORKERS_PREFIX + worker_id)

    async def live_workers(self) -> list[dict]:
        out = []
        async for key in self.redis.scan_iter(f"{WORKERS_PREFIX}*", count=100):
            info = await self.redis.hgetall(key)
            info["id"] = key.removeprefix(WORKERS_PREFIX)
            out.append(info)
        return out

    async def active_job_ids(self) -> set[str]:
        return {w["current_job"] for w in await self.live_workers() if w.get("current_job")}

    async def worker_status(self) -> dict:
        """Aggregate view for the dashboard."""
        try:
            workers = await self.live_workers()
        except Exception:  # Redis down — report offline instead of failing
            workers = []
        online = len(workers) > 0
        return {
            "worker_online": online,
            "chrome_connected": any(w.get("chrome") == "connected" for w in workers),
            "playwright_ready": online,
            "last_heartbeat": max((w.get("heartbeat", "") for w in workers), default=None),
            "current_job": next((w["current_job"] for w in workers if w.get("current_job")), None),
            "worker_count": len(workers),
        }

    # ---- cache ----
    async def clear_cache(self) -> int:
        deleted = 0
        async for key in self.redis.scan_iter(f"{CACHE_PREFIX}*", count=500):
            await self.redis.delete(key)
            deleted += 1
        return deleted
