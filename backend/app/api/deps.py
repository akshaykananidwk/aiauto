from __future__ import annotations

from datetime import datetime, timezone

import jwt as pyjwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token, hash_api_key
from app.db.session import get_db
from app.models.apikey import ApiKey
from app.models.user import User, UserRole
from app.repositories.user import UserRepository
from app.services.auth_guard import is_revoked

bearer = HTTPBearer(auto_error=False)


async def _user_from_api_key(api_key: str, db: AsyncSession) -> User | None:
    res = await db.execute(
        select(ApiKey).where(
            ApiKey.key_hash == hash_api_key(api_key), ApiKey.is_active.is_(True)
        )
    )
    key = res.scalar_one_or_none()
    if key is None:
        return None
    key.last_used_at = datetime.now(timezone.utc)
    return await UserRepository(db).get(key.user_id)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> User:
    user: User | None = None
    if credentials is not None:
        try:
            payload = decode_token(credentials.credentials, "access")
        except pyjwt.InvalidTokenError:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
        if await is_revoked(payload.get("jti", "")):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token has been revoked")
        user = await UserRepository(db).get(int(payload["sub"]))
    elif x_api_key:
        user = await _user_from_api_key(x_api_key, db)
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
    else:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive or not found")
    return user


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user
