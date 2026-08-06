from __future__ import annotations

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import bearer, get_current_user
from app.core.security import create_file_token, decode_token
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


async def _resolve_file(
    file_id: int,
    st: str | None,
    credentials: HTTPAuthorizationCredentials | None,
    db: AsyncSession,
) -> PromptFile:
    """Authorize via a signed one-file token (?st=…) OR the normal JWT."""
    if st:
        try:
            payload = decode_token(st, "file")
        except pyjwt.InvalidTokenError:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired file link")
        if payload.get("sub") != str(file_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Link does not match this file")
        file = await db.get(PromptFile, file_id)
        if file is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
        return file
    user = await get_current_user(credentials, db)
    return await _get_authorized_file(file_id, user, db)


@router.get("/{file_id}/link")
async def file_link(
    file_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Mint a short-lived direct URL for this file. The browser can use it
    natively (<a download>, <img src>, new tab) so saving works everywhere,
    including mobile galleries."""
    file = await _get_authorized_file(file_id, user, db)
    token = create_file_token(file_id)
    return {
        "url": f"/api/v1/files/{file_id}/download?st={token}",
        "filename": file.filename,
        "mime_type": file.mime_type,
        "expires_in_seconds": 15 * 60,
    }


@router.get("/{file_id}/download")
async def download_file(
    file_id: int,
    st: str | None = Query(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    file = await _resolve_file(file_id, st, credentials, db)
    path = StorageService().abs_path(file.rel_path)
    if not path.exists():
        raise HTTPException(status.HTTP_410_GONE, "File no longer on disk")
    return FileResponse(path, media_type=file.mime_type, filename=file.filename)


@router.get("/{file_id}/thumbnail")
async def file_thumbnail(
    file_id: int,
    st: str | None = Query(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    file = await _resolve_file(file_id, st, credentials, db)
    if not file.thumb_rel_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No thumbnail")
    path = StorageService().abs_path(file.thumb_rel_path)
    if not path.exists():
        raise HTTPException(status.HTTP_410_GONE, "Thumbnail no longer on disk")
    return FileResponse(path, media_type="image/png")
