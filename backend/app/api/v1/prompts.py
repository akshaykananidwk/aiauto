from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.prompt import Prompt, PromptStatus
from app.models.user import User, UserRole
from app.repositories.prompt import PromptRepository
from app.schemas.prompt import FileOut, PromptCreate, PromptListOut, PromptOut
from app.schemas.quota import QuotaUsageOut
from app.services.prompt import PromptService
from app.services.queue import QueueService
from app.services.quota import QuotaService, QuotaExceededError

router = APIRouter(prefix="/prompts", tags=["prompts"])


def to_out(prompt: Prompt, queue_position: int | None = None) -> PromptOut:
    out = PromptOut.model_validate(prompt)
    out.user_name = prompt.user.full_name or prompt.user.username if prompt.user else ""
    out.files = [
        FileOut(
            id=f.id, kind=f.kind, filename=f.filename, mime_type=f.mime_type,
            size_bytes=f.size_bytes, has_thumbnail=f.thumb_rel_path is not None,
            created_at=f.created_at,
        )
        for f in prompt.files
    ]
    out.queue_position = queue_position
    return out


async def get_accessible_prompt(
    prompt_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Prompt:
    prompt = await PromptRepository(db).get(prompt_id)
    if prompt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Prompt not found")
    if user.role != UserRole.admin and prompt.user_id != user.id:
        # staff must never see other people's prompts
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Prompt not found")
    return prompt


@router.post("", response_model=PromptOut, status_code=201)
async def submit_prompt(
    prompt_text: str = Form(min_length=1, max_length=32000),
    wants_image: bool = Form(False),
    priority: int = Form(0, ge=0, le=10),
    computer_name: str = Form("", max_length=128),
    files: list[UploadFile] = File(default=[]),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PromptOut:
    data = PromptCreate(
        prompt_text=prompt_text, wants_image=wants_image,
        priority=priority, computer_name=computer_name,
    )
    try:
        prompt = await PromptService(db).submit(user, data, files)
    except QuotaExceededError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc))
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    position = await QueueService().position(prompt.id)
    return to_out(prompt, position)


@router.get("/quota", response_model=QuotaUsageOut)
async def my_quota(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> QuotaUsageOut:
    return QuotaUsageOut(**await QuotaService(db).usage(user))


@router.get("/image-instruction")
async def image_instruction(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    """The English instruction automatically appended to image prompts, so
    the web app can show staff exactly what will be sent."""
    from app.services.app_settings import AppSettingsService

    settings = await AppSettingsService(db).effective()
    return {"instruction": settings.image_prompt_instruction}


@router.get("/export")
async def export_my_history(
    fmt: str = Query(default="json", pattern="^(json|csv)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export the caller's full prompt history (conversation backup)."""
    items, _ = await PromptRepository(db).list(user_id=user.id, page=1, page_size=10000)
    if fmt == "json":
        payload = [
            {
                "id": p.id, "prompt": p.prompt_text, "response": p.response_text,
                "status": p.status.value,
                "created_at": p.created_at.isoformat(),
                "files": [f.filename for f in p.files],
            }
            for p in items
        ]
        return JSONResponse(
            payload,
            headers={"Content-Disposition": "attachment; filename=prompt_history.json"},
        )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "created_at", "status", "prompt", "response"])
    for p in items:
        writer.writerow([p.id, p.created_at.isoformat(), p.status.value,
                         p.prompt_text, p.response_text or ""])
    return Response(
        buf.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=prompt_history.csv"},
    )


@router.get("", response_model=PromptListOut)
async def list_prompts(
    status_filter: PromptStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, max_length=200),
    all_users: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PromptListOut:
    # staff are always limited to their own prompts
    user_filter = None if (all_users and user.role == UserRole.admin) else user.id
    items, total = await PromptRepository(db).list(
        user_id=user_filter, status=status_filter, search=search,
        page=page, page_size=page_size,
    )
    return PromptListOut(
        items=[to_out(p) for p in items], total=total, page=page, page_size=page_size
    )


@router.get("/{prompt_id}", response_model=PromptOut)
async def get_prompt(
    prompt: Prompt = Depends(get_accessible_prompt),
) -> PromptOut:
    position = None
    if prompt.status == PromptStatus.waiting:
        position = await QueueService().position(prompt.id)
    return to_out(prompt, position)


@router.post("/{prompt_id}/cancel", response_model=PromptOut)
async def cancel_prompt(
    prompt: Prompt = Depends(get_accessible_prompt),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PromptOut:
    try:
        prompt = await PromptService(db).cancel(prompt, user)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return to_out(prompt)


@router.post("/{prompt_id}/retry", response_model=PromptOut)
async def retry_prompt(
    prompt: Prompt = Depends(get_accessible_prompt),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PromptOut:
    try:
        prompt = await PromptService(db).retry(prompt, user)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return to_out(prompt)
