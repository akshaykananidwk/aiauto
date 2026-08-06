from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.security import generate_api_key
from app.db.session import get_db
from app.models.apikey import ApiKey
from app.models.user import User
from app.schemas.apikey import ApiKeyCreate, ApiKeyCreated, ApiKeyOut
from app.services.audit import audit

router = APIRouter(prefix="/api-keys", tags=["api-keys"])

MAX_KEYS_PER_USER = 10


@router.get("", response_model=list[ApiKeyOut])
async def list_api_keys(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[ApiKey]:
    res = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc())
    )
    return list(res.scalars().all())


@router.post("", response_model=ApiKeyCreated, status_code=201)
async def create_api_key(
    body: ApiKeyCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyCreated:
    res = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.is_active.is_(True))
    )
    if len(res.scalars().all()) >= MAX_KEYS_PER_USER:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Maximum {MAX_KEYS_PER_USER} active API keys per user — "
                            "revoke one first")
    plain, key_hash, prefix = generate_api_key()
    key = ApiKey(user_id=user.id, name=body.name, prefix=prefix, key_hash=key_hash)
    db.add(key)
    await audit(db, "apikey.created", f"API key '{body.name}' created", user_id=user.id)
    await db.commit()
    await db.refresh(key)
    return ApiKeyCreated(
        id=key.id, name=key.name, prefix=key.prefix, is_active=key.is_active,
        last_used_at=key.last_used_at, created_at=key.created_at, plain_key=plain,
    )


@router.delete("/{key_id}")
async def revoke_api_key(
    key_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    key = await db.get(ApiKey, key_id)
    if key is None or key.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found")
    key.is_active = False
    await audit(db, "apikey.revoked", f"API key '{key.name}' revoked", user_id=user.id)
    await db.commit()
    return {"ok": True}
