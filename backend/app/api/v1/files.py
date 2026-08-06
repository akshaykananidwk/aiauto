from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.file import PromptFile
from app.models.prompt import Prompt
from app.models.user import User, UserRole
from app.services.storage import StorageService

router = APIRouter(prefix="/files", tags=["files"])


async def _get_authorized_file(
    file_id: int, user: User, db: AsyncSession
) -> PromptFile:
    res = await db.execute(
        select(PromptFile, Prompt).join(Prompt, PromptFile.prompt_id == Prompt.id)
        .where(PromptFile.id == file_id)
    )
    row = res.first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    file, prompt = row
    if user.role != UserRole.admin and prompt.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    return file


@router.get("/{file_id}/download")
async def download_file(
    file_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    file = await _get_authorized_file(file_id, user, db)
    path = StorageService().abs_path(file.rel_path)
    if not path.exists():
        raise HTTPException(status.HTTP_410_GONE, "File no longer on disk")
    return FileResponse(path, media_type=file.mime_type, filename=file.filename)


@router.get("/{file_id}/thumbnail")
async def file_thumbnail(
    file_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    file = await _get_authorized_file(file_id, user, db)
    if not file.thumb_rel_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No thumbnail")
    path = StorageService().abs_path(file.thumb_rel_path)
    if not path.exists():
        raise HTTPException(status.HTTP_410_GONE, "Thumbnail no longer on disk")
    return FileResponse(path, media_type="image/png")
