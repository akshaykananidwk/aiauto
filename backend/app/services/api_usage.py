"""Per-API-key usage counters and rate limiting (Redis-backed)."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from app.services.redis_client import get_redis

USAGE_PREFIX = "aiauto:apiusage:"          # {key_id}:{yyyy-mm-dd}:{ok|err}
RATELIMIT_PREFIX = "aiauto:apiratelimit:"  # {key_id}:{minute-window}
DEFAULT_RATE_LIMIT = 60  # requests/minute when the key has no override


async def check_rate_limit(key_id: int, per_minute: int) -> tuple[bool, int]:
    """Fixed-window per-key limit. Returns (allowed, remaining)."""
    limit = per_minute or DEFAULT_RATE_LIMIT
    window = int(time.time() // 60)
    redis_key = f"{RATELIMIT_PREFIX}{key_id}:{window}"
    try:
        redis = get_redis()
        count = await redis.incr(redis_key)
        if count == 1:
            await redis.expire(redis_key, 70)
        return count <= limit, max(0, limit - count)
    except Exception:
        return True, limit  # Redis down — don't block traffic


async def record_request(key_id: int, ok: bool) -> None:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        redis = get_redis()
        redis_key = f"{USAGE_PREFIX}{key_id}:{day}:{'ok' if ok else 'err'}"
        await redis.incr(redis_key)
        await redis.expire(redis_key, 40 * 86400)
    except Exception:
        pass


async def usage_stats(key_ids: list[int], days: int = 7) -> dict:
    """Aggregated ok/err counts per day across the given keys."""
    out: dict = {"days": [], "total_ok": 0, "total_err": 0}
    try:
        redis = get_redis()
        today = datetime.now(timezone.utc).date()
        for offset in range(days - 1, -1, -1):
            day = str(today - timedelta(days=offset))
            ok = err = 0
            for key_id in key_ids:
                ok += int(await redis.get(f"{USAGE_PREFIX}{key_id}:{day}:ok") or 0)
                err += int(await redis.get(f"{USAGE_PREFIX}{key_id}:{day}:err") or 0)
            out["days"].append({"day": day, "ok": ok, "err": err})
            out["total_ok"] += ok
            out["total_err"] += err
    except Exception:
        pass
    return out
