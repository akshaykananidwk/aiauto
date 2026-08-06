"""AIAuto public REST API v1.

Integrate any website, ERP, CRM, desktop or mobile app with the central
AI platform. Every job is processed internally by the master computer's
ChatGPT Pro browser session — there are no third-party AI APIs involved.

Authentication: `X-API-Key: ak_…` (create keys on the platform's API page).
Full guide: docs/PUBLIC_API.md · Interactive explorer: /api/docs
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.public_deps import ApiAuth, get_api_auth
from app.core.security import encrypt_secret, generate_webhook_secret
from app.db.session import get_db
from app.models.file import PromptFile
from app.models.prompt import Prompt, PromptStatus
from app.models.user import UserRole
from app.models.webhook import WEBHOOK_EVENTS, Webhook
from app.repositories.prompt import PromptRepository
from app.schemas.prompt import PromptCreate
from app.services import webhooks as webhook_service
from app.services.prompt import PromptService
from app.services.queue import QueueService
from app.services.quota import QuotaExceededError

router = APIRouter(prefix="/api/public/v1", tags=["public-api"])

PROGRESS = {"waiting": 10, "processing": 55, "completed": 100, "failed": 100, "cancelled": 100}


async def job_out(prompt: Prompt, queue_position: int | None = None) -> dict:
    return {
        "id": prompt.id,
        "type": "image" if prompt.wants_image else "text",
        "status": prompt.status.value,
        "progress": PROGRESS.get(prompt.status.value, 0),
        "queue_position": queue_position,
        "prompt": prompt.prompt_text,
        "response": prompt.response_text,
        "error": prompt.error,
        "created_at": prompt.created_at,
        "started_at": prompt.started_at,
        "completed_at": prompt.completed_at,
        "files": [
            {
                "id": f.id,
                "name": f.filename,
                "kind": f.kind.value,
                "mime_type": f.mime_type,
                "size_bytes": f.size_bytes,
                "url": f"/api/public/v1/files/{f.id}",
            }
            for f in prompt.files
        ],
    }


@router.get("/me")
async def me(auth: ApiAuth = Depends(get_api_auth), request: Request = None) -> dict:
    """Identify the calling key and its limits."""
    key = auth.key
    return {
        "user": {"username": auth.user.username, "department": auth.user.department},
        "key": {
            "name": key.name,
            "prefix": key.prefix,
            "scopes": key.scopes or "all",
            "rate_limit_per_minute": key.rate_limit_per_minute or 60,
            "expires_at": key.expires_at,
        },
    }


# ---------------- jobs ----------------

async def _submit(auth: ApiAuth, db: AsyncSession, prompt_text: str,
                  wants_image: bool, uploads: list[UploadFile]) -> dict:
    auth.require("jobs:write")
    data = PromptCreate(prompt_text=prompt_text, wants_image=wants_image,
                        computer_name="public-api")
    try:
        prompt = await PromptService(db).submit(auth.user, data, uploads)
    except QuotaExceededError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc))
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    position = await QueueService().position(prompt.id)  # job.submitted webhook
    return await job_out(prompt, position)               # fires in PromptService


@router.post("/jobs", status_code=201)
async def create_job(
    prompt: str = Form(min_length=1, max_length=32000),
    type: str = Form(default="text", pattern="^(text|image)$"),
    files: list[UploadFile] = File(default=[]),
    auth: ApiAuth = Depends(get_api_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Submit a job (multipart — supports file uploads: images, PDF, DOCX,
    XLSX, TXT, ZIP…). Returns the job with its `id` for polling."""
    return await _submit(auth, db, prompt, type == "image", files)


class TextRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=32000)


@router.post("/text", status_code=201)
async def generate_text(
    body: TextRequest,
    auth: ApiAuth = Depends(get_api_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Convenience JSON endpoint: submit a text-generation job."""
    return await _submit(auth, db, body.prompt, False, [])


@router.post("/images", status_code=201)
async def generate_image(
    body: TextRequest,
    auth: ApiAuth = Depends(get_api_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Convenience JSON endpoint: submit an image-generation job."""
    return await _submit(auth, db, body.prompt, True, [])


@router.get("/jobs")
async def list_jobs(
    status_filter: PromptStatus | None = Query(default=None, alias="status"),
    type: str | None = Query(default=None, pattern="^(text|image)$"),
    created_after: datetime | None = Query(default=None),
    created_before: datetime | None = Query(default=None),
    all_users: bool = Query(default=False, description="admins only"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    auth: ApiAuth = Depends(get_api_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    auth.require("jobs:read")
    user_filter = None if (all_users and auth.user.role == UserRole.admin) else auth.user.id
    items, total = await PromptRepository(db).list(
        user_id=user_filter, status=status_filter,
        created_after=created_after, created_before=created_before,
        page=page, page_size=page_size,
    )
    if type:
        items = [p for p in items if p.wants_image == (type == "image")]
    return {
        "items": [await job_out(p) for p in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def _get_job(job_id: str, auth: ApiAuth, db: AsyncSession) -> Prompt:
    prompt = await PromptRepository(db).get(job_id)
    if prompt is None or (auth.user.role != UserRole.admin
                          and prompt.user_id != auth.user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    return prompt


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    auth: ApiAuth = Depends(get_api_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    auth.require("jobs:read")
    prompt = await _get_job(job_id, auth, db)
    position = None
    if prompt.status == PromptStatus.waiting:
        position = await QueueService().position(prompt.id)
    return await job_out(prompt, position)


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    auth: ApiAuth = Depends(get_api_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    auth.require("jobs:write")
    prompt = await _get_job(job_id, auth, db)
    try:
        prompt = await PromptService(db).cancel(prompt, auth.user)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return await job_out(prompt)


@router.post("/jobs/{job_id}/retry")
async def retry_job(
    job_id: str,
    auth: ApiAuth = Depends(get_api_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    auth.require("jobs:write")
    prompt = await _get_job(job_id, auth, db)
    try:
        prompt = await PromptService(db).retry(prompt, auth.user)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return await job_out(prompt)


# ---------------- files ----------------

@router.get("/files/{file_id}")
async def download_file(
    file_id: int,
    auth: ApiAuth = Depends(get_api_auth),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Download a result or uploaded file belonging to one of your jobs."""
    auth.require("files:read")
    res = await db.execute(
        select(PromptFile, Prompt).join(Prompt, PromptFile.prompt_id == Prompt.id)
        .where(PromptFile.id == file_id)
    )
    row = res.first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "file not found")
    file, prompt = row
    if auth.user.role != UserRole.admin and prompt.user_id != auth.user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "file not found")
    from app.services.storage import StorageService

    path = StorageService().abs_path(file.rel_path)
    if not path.exists():
        raise HTTPException(status.HTTP_410_GONE, "file no longer on disk")
    return FileResponse(path, media_type=file.mime_type, filename=file.filename)


# ---------------- webhooks ----------------

def _webhook_out(hook: Webhook, secret_plain: str | None = None) -> dict:
    out = {
        "id": hook.id,
        "url": hook.url,
        "events": hook.events or "all",
        "is_active": hook.is_active,
        "last_status": hook.last_status,
        "last_delivery_at": hook.last_delivery_at,
        "failure_count": hook.failure_count,
        "created_at": hook.created_at,
    }
    if secret_plain:
        out["secret"] = secret_plain  # shown exactly once, at creation
    return out


class WebhookCreate(BaseModel):
    url: str = Field(min_length=8, max_length=512, pattern=r"^https?://.+")
    events: list[str] | None = None


class WebhookUpdate(BaseModel):
    url: str | None = Field(default=None, min_length=8, max_length=512,
                            pattern=r"^https?://.+")
    events: list[str] | None = None
    is_active: bool | None = None


@router.get("/webhooks")
async def list_webhooks(
    auth: ApiAuth = Depends(get_api_auth), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    auth.require("webhooks:manage")
    res = await db.execute(select(Webhook).where(Webhook.user_id == auth.user.id))
    return [_webhook_out(h) for h in res.scalars().all()]


@router.post("/webhooks", status_code=201)
async def create_webhook(
    body: WebhookCreate,
    auth: ApiAuth = Depends(get_api_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    auth.require("webhooks:manage")
    if body.events:
        unknown = set(body.events) - set(WEBHOOK_EVENTS)
        if unknown:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"unknown events: {sorted(unknown)}")
    res = await db.execute(select(Webhook).where(Webhook.user_id == auth.user.id))
    if len(res.scalars().all()) >= 10:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "maximum 10 webhooks per user")
    secret = generate_webhook_secret()
    hook = Webhook(user_id=auth.user.id, url=body.url,
                   secret_encrypted=encrypt_secret(secret), events=body.events)
    db.add(hook)
    await db.commit()
    await db.refresh(hook)
    return _webhook_out(hook, secret_plain=secret)


async def _get_webhook(hook_id: int, auth: ApiAuth, db: AsyncSession) -> Webhook:
    hook = await db.get(Webhook, hook_id)
    if hook is None or hook.user_id != auth.user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "webhook not found")
    return hook


@router.patch("/webhooks/{hook_id}")
async def update_webhook(
    hook_id: int,
    body: WebhookUpdate,
    auth: ApiAuth = Depends(get_api_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    auth.require("webhooks:manage")
    hook = await _get_webhook(hook_id, auth, db)
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(hook, key, value)
    await db.commit()
    await db.refresh(hook)
    return _webhook_out(hook)


@router.delete("/webhooks/{hook_id}")
async def delete_webhook(
    hook_id: int,
    auth: ApiAuth = Depends(get_api_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    auth.require("webhooks:manage")
    hook = await _get_webhook(hook_id, auth, db)
    await db.delete(hook)
    await db.commit()
    return {"ok": True}


@router.post("/webhooks/{hook_id}/test")
async def test_webhook(
    hook_id: int,
    auth: ApiAuth = Depends(get_api_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    auth.require("webhooks:manage")
    hook = await _get_webhook(hook_id, auth, db)
    import asyncio

    from app.core.security import decrypt_secret

    secret = decrypt_secret(hook.secret_encrypted)
    asyncio.get_running_loop().create_task(webhook_service._deliver(
        hook.id, hook.url, secret, "job.completed",
        {"job_id": "test", "test": True, "message": "AIAuto webhook test delivery"},
    ))
    return {"scheduled_deliveries": 1}
