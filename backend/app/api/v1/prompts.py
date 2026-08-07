from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
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
    image_size: str = Form("auto", max_length=32),
    files: list[UploadFile] = File(default=[]),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PromptOut:
    data = PromptCreate(
        prompt_text=prompt_text, wants_image=wants_image,
        priority=priority, computer_name=computer_name, image_size=image_size,
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


@router.get("/image-sizes")
async def image_sizes(_: User = Depends(get_current_user)) -> dict:
    """Available output size presets for image jobs."""
    from app.services.image_presets import DEFAULT_PRESET, presets_list

    return {"presets": presets_list(), "default": DEFAULT_PRESET}


class ImproveRequest(BaseModel):
    prompt_text: str = Field(min_length=1, max_length=8000)
    wants_image: bool = False


@router.post("/improve", status_code=201)
async def improve_prompt(
    body: ImproveRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Ask the AI to rewrite a rough request into a better prompt.

    Runs as a short, high-priority helper job so it comes back in seconds
    instead of waiting behind long image jobs. Poll `/prompts/improve/{id}`.
    """
    from app.services.prompt_builder import build_improve_prompt

    data = PromptCreate(
        prompt_text=build_improve_prompt(body.prompt_text, body.wants_image),
        wants_image=False, computer_name="prompt-improver", is_utility=True,
    )
    try:
        prompt = await PromptService(db).submit(user, data, [])
    except QuotaExceededError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc))
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return {"id": prompt.id, "status": prompt.status.value}


@router.get("/improve/{prompt_id}")
async def improve_result(
    prompt: Prompt = Depends(get_accessible_prompt),
) -> dict:
    """Status/result of a prompt-improvement job."""
    from app.services.prompt_builder import clean_improved_text

    if not prompt.is_utility:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not an improvement job")
    return {
        "id": prompt.id,
        "status": prompt.status.value,
        "improved_text": (clean_improved_text(prompt.response_text)
                          if prompt.status == PromptStatus.completed else None),
        "error": prompt.error,
    }


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
    only_images: bool | None = Query(default=None),
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
        wants_image=only_images, page=page, page_size=page_size,
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


class FollowUpRequest(BaseModel):
    prompt_text: str = Field(min_length=1, max_length=32000)
    wants_image: bool = False
    image_size: str = Field(default="auto", max_length=32)


@router.post("/{prompt_id}/follow-up", response_model=PromptOut, status_code=201)
async def follow_up(
    body: FollowUpRequest,
    prompt: Prompt = Depends(get_accessible_prompt),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PromptOut:
    """Ask another question about the same job — the AI continues the
    original conversation (or is given it as context if that chat is gone)."""
    if prompt.status != PromptStatus.completed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "only completed jobs can be followed up")
    data = PromptCreate(
        prompt_text=body.prompt_text, wants_image=body.wants_image,
        image_size=body.image_size, computer_name=prompt.computer_name,
        # the thread root: following up on a follow-up keeps one chain
        follow_up_to=prompt.id,
    )
    try:
        new_prompt = await PromptService(db).submit(user, data, [])
    except QuotaExceededError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc))
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    position = await QueueService().position(new_prompt.id)
    return to_out(new_prompt, position)


@router.get("/{prompt_id}/thread", response_model=list[PromptOut])
async def prompt_thread(
    prompt: Prompt = Depends(get_accessible_prompt),
    db: AsyncSession = Depends(get_db),
) -> list[PromptOut]:
    """Follow-up jobs that continue this one, oldest first."""
    from sqlalchemy import select

    rows = (await db.execute(
        select(Prompt).where(Prompt.follow_up_to == prompt.id)
        .order_by(Prompt.created_at)
    )).scalars().unique().all()
    return [to_out(p) for p in rows]


@router.get("/{prompt_id}/audio")
async def prompt_audio(
    prompt: Prompt = Depends(get_accessible_prompt),
    db: AsyncSession = Depends(get_db),
):
    """Download the answer as an audio file (generated once, then cached)."""
    from fastapi.responses import FileResponse

    from app.services.app_settings import AppSettingsService
    from app.services.tts import TTSUnavailable, synthesize

    if not (prompt.response_text or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "this job has no text answer to read aloud")
    settings = await AppSettingsService(db).effective()
    try:
        path, mime = await synthesize(
            prompt.id, prompt.response_text,
            engine=settings.tts_engine, language=settings.tts_language)
    except TTSUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    return FileResponse(path, media_type=mime,
                        filename=f"answer_{prompt.id[:8]}{path.suffix}")


@router.post("/{prompt_id}/regenerate", response_model=PromptOut, status_code=201)
async def regenerate_prompt(
    prompt: Prompt = Depends(get_accessible_prompt),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PromptOut:
    """Run the same request again as a new job — the previous result is
    kept, so both versions can be compared."""
    try:
        new_prompt = await PromptService(db).regenerate(prompt, user)
    except QuotaExceededError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc))
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    position = await QueueService().position(new_prompt.id)
    return to_out(new_prompt, position)


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
