from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.prompt import Prompt, PromptStatus
from app.models.user import User, UserRole
from app.repositories.prompt import PromptRepository
from app.schemas.prompt import FileOut, PromptCreate, PromptListOut, PromptOut
from app.services.prompt import PromptService
from app.services.queue import QueueService

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
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    position = await QueueService().position(prompt.id)
    return to_out(prompt, position)


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
