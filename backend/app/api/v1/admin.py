"""Admin-only endpoints: live queue view, audit logs, settings."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.api.v1.prompts import to_out
from app.db.session import get_db
from app.repositories.audit import AuditRepository
from app.repositories.prompt import PromptRepository
from app.schemas.prompt import PromptOut
from app.schemas.settings import AdminSettings, AdminSettingsUpdate
from app.services.app_settings import AppSettingsService
from app.services.queue import QueueService

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("/queue", response_model=list[PromptOut])
async def live_queue(db: AsyncSession = Depends(get_db)) -> list[PromptOut]:
    """Waiting prompts in execution order, plus the currently running job."""
    queue = QueueService()
    repo = PromptRepository(db)
    out: list[PromptOut] = []

    status = await queue.worker_status()
    if status.get("current_job"):
        current = await repo.get(status["current_job"])
        if current is not None:
            out.append(to_out(current))

    for position, prompt_id in enumerate(await queue.pending_ids(200), start=1):
        prompt = await repo.get(prompt_id)
        if prompt is not None:
            out.append(to_out(prompt, position))
    return out


@router.get("/logs")
async def audit_logs(
    event: str | None = Query(default=None, max_length=64),
    level: str | None = Query(default=None, max_length=16),
    user_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    items, total = await AuditRepository(db).list(
        event=event, level=level, user_id=user_id, page=page, page_size=page_size
    )
    return {
        "items": [
            {
                "id": log.id,
                "user_id": log.user_id,
                "event": log.event,
                "level": log.level,
                "message": log.message,
                "meta": log.meta,
                "created_at": log.created_at,
            }
            for log in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/settings", response_model=AdminSettings)
async def get_settings_endpoint(db: AsyncSession = Depends(get_db)) -> AdminSettings:
    return await AppSettingsService(db).get()


@router.put("/settings", response_model=AdminSettings)
async def update_settings_endpoint(
    body: AdminSettingsUpdate, db: AsyncSession = Depends(get_db)
) -> AdminSettings:
    return await AppSettingsService(db).update(body)
