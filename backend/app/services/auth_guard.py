"""Brute-force lockout and JWT revocation, backed by Redis.

Fail-secure notes: if Redis is unreachable the lockout check allows the
attempt (login still requires the correct password) but revocation
checks REJECT the token — a revoked token must never slip through just
because Redis blinked.
"""
from __future__ import annotations

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.redis_client import get_redis

logger = get_logger("auth_guard")

FAIL_PREFIX = "aiauto:auth:fail:"
LOCK_PREFIX = "aiauto:auth:lock:"
REVOKED_PREFIX = "aiauto:auth:revoked:"


def _norm(username: str) -> str:
    return username.strip().lower()[:64]


async def is_locked(username: str) -> bool:
    try:
        return await get_redis().exists(LOCK_PREFIX + _norm(username)) > 0
    except Exception:
        return False


async def record_failure(username: str) -> int:
    """Record a failed login; lock the account after N failures."""
    settings = get_settings()
    try:
        redis = get_redis()
        key = FAIL_PREFIX + _norm(username)
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, settings.login_lockout_minutes * 60)
        if count >= settings.login_max_failures:
            await redis.set(LOCK_PREFIX + _norm(username), "1",
                            ex=settings.login_lockout_minutes * 60)
            logger.warning("account '%s' locked after %s failed logins", username, count)
        return count
    except Exception:
        return 0


async def clear_failures(username: str) -> None:
    try:
        redis = get_redis()
        await redis.delete(FAIL_PREFIX + _norm(username))
        await redis.delete(LOCK_PREFIX + _norm(username))
    except Exception:
        pass


async def revoke_jti(jti: str, ttl_seconds: int) -> None:
    if not jti:
        return
    try:
        await get_redis().set(REVOKED_PREFIX + jti, "1", ex=max(60, ttl_seconds))
    except Exception as exc:
        logger.error("failed to persist token revocation: %s", exc)


async def is_revoked(jti: str) -> bool:
    if not jti:
        return True  # tokens without a jti are never acceptable
    try:
        return await get_redis().exists(REVOKED_PREFIX + jti) > 0
    except Exception:
        logger.error("revocation check failed — rejecting token (fail secure)")
        return True
