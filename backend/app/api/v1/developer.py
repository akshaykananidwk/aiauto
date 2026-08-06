"""Developer portal (session-authenticated): manage the platform's OWN
public-API keys, webhooks, and view usage statistics."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.security import (
    decrypt_secret,
    encrypt_secret,
    generate_api_key,
    generate_webhook_secret,
)
from app.db.session import get_db
from app.models.apikey import API_SCOPES, ApiKey
from app.models.user import User
from app.models.webhook import WEBHOOK_EVENTS, Webhook
from app.services import webhooks as webhook_service
from app.services.api_usage import usage_stats
from app.services.audit import audit

router = APIRouter(prefix="/developer", tags=["developer"])

MAX_KEYS_PER_USER = 20


def _key_out(key: ApiKey, plain: str | None = None) -> dict:
    out = {
        "id": key.id,
        "name": key.name,
        "prefix": key.prefix,
        "is_active": key.is_active,
        "scopes": key.scopes or [],
        "expires_at": key.expires_at,
        "ip_allowlist": key.ip_allowlist or [],
        "rate_limit_per_minute": key.rate_limit_per_minute,
        "request_count": key.request_count,
        "last_used_at": key.last_used_at,
        "created_at": key.created_at,
    }
    if plain:
        out["plain_key"] = plain  # returned exactly once
    return out


class KeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: list[str] | None = None
    expires_at: datetime | None = None
    ip_allowlist: list[str] | None = None
    rate_limit_per_minute: int = Field(default=0, ge=0, le=10000)


class KeyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    scopes: list[str] | None = None
    expires_at: datetime | None = None
    ip_allowlist: list[str] | None = None
    rate_limit_per_minute: int | None = Field(default=None, ge=0, le=10000)
    is_active: bool | None = None


def _validate_scopes(scopes: list[str] | None) -> None:
    if scopes:
        unknown = set(scopes) - set(API_SCOPES)
        if unknown:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"unknown scopes: {sorted(unknown)} — valid: {API_SCOPES}")


@router.get("/scopes")
async def list_scopes(_: User = Depends(get_current_user)) -> dict:
    return {"scopes": API_SCOPES, "events": WEBHOOK_EVENTS}


@router.get("/keys")
async def list_keys(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    res = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc())
    )
    return [_key_out(k) for k in res.scalars().all()]


@router.post("/keys", status_code=201)
async def create_key(
    body: KeyCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _validate_scopes(body.scopes)
    res = await db.execute(select(ApiKey).where(ApiKey.user_id == user.id,
                                                ApiKey.is_active.is_(True)))
    if len(res.scalars().all()) >= MAX_KEYS_PER_USER:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"maximum {MAX_KEYS_PER_USER} active API keys per user")
    plain, key_hash, prefix = generate_api_key()
    key = ApiKey(
        user_id=user.id, name=body.name, prefix=prefix, key_hash=key_hash,
        scopes=body.scopes, expires_at=body.expires_at,
        ip_allowlist=body.ip_allowlist,
        rate_limit_per_minute=body.rate_limit_per_minute,
    )
    db.add(key)
    await audit(db, "apikey.created", f"API key '{body.name}' created", user_id=user.id)
    await db.commit()
    await db.refresh(key)
    return _key_out(key, plain=plain)


async def _get_own_key(key_id: int, user: User, db: AsyncSession) -> ApiKey:
    key = await db.get(ApiKey, key_id)
    if key is None or key.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found")
    return key


@router.patch("/keys/{key_id}")
async def update_key(
    key_id: int,
    body: KeyUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _validate_scopes(body.scopes)
    key = await _get_own_key(key_id, user, db)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(key, field, value)
    await audit(db, "apikey.updated", f"API key '{key.name}' updated", user_id=user.id)
    await db.commit()
    await db.refresh(key)
    return _key_out(key)


@router.post("/keys/{key_id}/regenerate")
async def regenerate_key(
    key_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Replace the secret; the old key value stops working immediately."""
    key = await _get_own_key(key_id, user, db)
    plain, key_hash, prefix = generate_api_key()
    key.key_hash = key_hash
    key.prefix = prefix
    key.is_active = True
    await audit(db, "apikey.regenerated", f"API key '{key.name}' regenerated",
                user_id=user.id)
    await db.commit()
    await db.refresh(key)
    return _key_out(key, plain=plain)


@router.delete("/keys/{key_id}")
async def delete_key(
    key_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    key = await _get_own_key(key_id, user, db)
    await audit(db, "apikey.deleted", f"API key '{key.name}' deleted", user_id=user.id)
    await db.delete(key)
    await db.commit()
    return {"ok": True}


@router.get("/usage")
async def developer_usage(
    days: int = 7,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    res = await db.execute(select(ApiKey).where(ApiKey.user_id == user.id))
    keys = list(res.scalars().all())
    stats = await usage_stats([k.id for k in keys], days=min(max(days, 1), 30))
    total = stats["total_ok"] + stats["total_err"]
    return {
        **stats,
        "total_requests": total,
        "active_keys": sum(1 for k in keys if k.is_active),
        "success_rate": round(stats["total_ok"] / total * 100, 1) if total else None,
    }


# ---- webhooks (same objects as the public API, managed from the UI) ----

@router.get("/webhooks")
async def list_webhooks(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    from app.api.public_v1 import _webhook_out

    res = await db.execute(select(Webhook).where(Webhook.user_id == user.id))
    return [_webhook_out(h) for h in res.scalars().all()]


class WebhookCreate(BaseModel):
    url: str = Field(min_length=8, max_length=512, pattern=r"^https?://.+")
    events: list[str] | None = None


@router.post("/webhooks", status_code=201)
async def create_webhook(
    body: WebhookCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.api.public_v1 import _webhook_out

    if body.events:
        unknown = set(body.events) - set(WEBHOOK_EVENTS)
        if unknown:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"unknown events: {sorted(unknown)}")
    res = await db.execute(select(Webhook).where(Webhook.user_id == user.id))
    if len(res.scalars().all()) >= 10:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "maximum 10 webhooks per user")
    secret = generate_webhook_secret()
    hook = Webhook(user_id=user.id, url=body.url,
                   secret_encrypted=encrypt_secret(secret), events=body.events)
    db.add(hook)
    await db.commit()
    await db.refresh(hook)
    return _webhook_out(hook, secret_plain=secret)


@router.delete("/webhooks/{hook_id}")
async def delete_webhook(
    hook_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    hook = await db.get(Webhook, hook_id)
    if hook is None or hook.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "webhook not found")
    await db.delete(hook)
    await db.commit()
    return {"ok": True}


@router.post("/webhooks/{hook_id}/test")
async def test_webhook(
    hook_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    import asyncio

    hook = await db.get(Webhook, hook_id)
    if hook is None or hook.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "webhook not found")
    secret = decrypt_secret(hook.secret_encrypted)
    asyncio.get_running_loop().create_task(webhook_service._deliver(
        hook.id, hook.url, secret, "job.completed",
        {"job_id": "test", "test": True, "message": "AIAuto webhook test delivery"},
    ))
    return {"scheduled_deliveries": 1}
