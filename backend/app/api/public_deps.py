"""Authentication/authorization for the platform's public REST API.

Keys are sent as `X-API-Key: ak_…`. Every request is checked for:
key validity, active flag, expiry, IP allowlist, scopes, and the
per-key rate limit. Usage is recorded for the developer dashboard.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_api_key
from app.db.session import get_db
from app.models.apikey import ApiKey
from app.models.user import User
from app.services.api_usage import check_rate_limit
from app.repositories.user import UserRepository


class ApiAuth:
    def __init__(self, user: User, key: ApiKey):
        self.user = user
        self.key = key

    def require(self, scope: str) -> None:
        scopes = self.key.scopes or []
        if scopes and scope not in scopes:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"this API key does not have the '{scope}' permission",
            )


async def get_api_auth(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> ApiAuth:
    if not x_api_key:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "missing X-API-Key header — create a key in the platform's API page",
        )
    res = await db.execute(select(ApiKey).where(ApiKey.key_hash == hash_api_key(x_api_key)))
    key = res.scalar_one_or_none()
    if key is None or not key.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or disabled API key")
    if key.expires_at is not None and key.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API key has expired")

    client_ip = request.client.host if request.client else ""
    if key.ip_allowlist and client_ip not in key.ip_allowlist:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            f"requests from IP {client_ip} are not allowed for this key")

    allowed, remaining = await check_rate_limit(key.id, key.rate_limit_per_minute)
    if not allowed:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "API key rate limit exceeded — slow down",
                            headers={"Retry-After": "60"})

    user = await UserRepository(db).get(key.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "key owner is inactive")

    key.last_used_at = datetime.now(timezone.utc)
    key.request_count += 1
    # committed together with whatever the endpoint does (or on request end)
    request.state.api_key_id = key.id
    request.state.api_rate_remaining = remaining
    return ApiAuth(user, key)
