"""Admin system endpoints: live health, resource monitoring, worker list,
manual backups and the restore wizard."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.models.user import User
from app.services.audit import audit
from app.services.system import SystemService
from app.services.update import run_state

router = APIRouter(prefix="/admin/system", tags=["system"],
                   dependencies=[Depends(get_current_admin)])


@router.get("/health")
async def system_health(db: AsyncSession = Depends(get_db)) -> dict:
    return await SystemService(db).health()


@router.get("/backups")
async def list_backups(db: AsyncSession = Depends(get_db)) -> list[dict]:
    return SystemService(db).list_backups()


@router.post("/backups", status_code=201)
async def create_backup(
    admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> dict:
    if run_state()["running"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "An update is running — try again later")
    try:
        result = await SystemService(db).create_backup()
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Backup failed: {exc}")
    await audit(db, "backup.manual", f"manual backup: {result['backup']}",
                user_id=admin.id, commit=True)
    return result


@router.post("/backups/restore")
async def restore_backup(
    name: str = Body(embed=True, min_length=1, max_length=200),
    confirm: bool = Body(embed=True, default=False),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not confirm:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Pass confirm=true to restore — this overwrites current code files")
    if run_state()["running"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "An update is running — try again later")
    svc = SystemService(db)
    try:
        result = await svc.restore_backup(name)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Backup not found")
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    await audit(db, "backup.restored", f"restored backup {name}", user_id=admin.id,
                level="warning", commit=True)
    return result


# ---- image-capture diagnostics -------------------------------------------
# When the worker cannot capture a generated image it saves a full-page
# screenshot + HTML dump to logs/. These endpoints surface those dumps and
# the log tails in the admin UI, so the exact failure on the master
# computer is visible in the website instead of guessed at.

import re  # noqa: E402
from pathlib import Path  # noqa: E402

from fastapi import Query  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402

from app.core.config import ROOT_DIR  # noqa: E402

_DIAG_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")
_DIAG_SUFFIXES = {".png", ".html", ".log"}


def _logs_dir() -> Path:
    d = ROOT_DIR / "logs"
    d.mkdir(exist_ok=True)
    return d


def _safe_diag_path(name: str) -> Path:
    if not _DIAG_NAME_RE.fullmatch(name) or ".." in name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid file name")
    path = (_logs_dir() / name).resolve()
    if (path.parent != _logs_dir().resolve()
            or path.suffix.lower() not in _DIAG_SUFFIXES):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid file name")
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    return path


@router.get("/diagnostics")
async def diagnostics() -> dict:
    """Debug dumps (newest first) + available log files."""
    from datetime import datetime, timezone

    def entry(p: Path) -> dict:
        st = p.stat()
        return {"name": p.name, "size_bytes": st.st_size,
                "modified": datetime.fromtimestamp(
                    st.st_mtime, tz=timezone.utc).isoformat()}

    dumps = sorted(_logs_dir().glob("debug_*.*"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    logs = [p for p in (_logs_dir() / "aiauto.log", _logs_dir() / "worker.log")
            if p.is_file()]
    return {"debug_dumps": [entry(p) for p in dumps[:50]],
            "logs": [entry(p) for p in logs]}


@router.get("/diagnostics/file")
async def diagnostics_file(name: str = Query(min_length=1)) -> FileResponse:
    path = _safe_diag_path(name)
    media = {"png": "image/png", "html": "text/html; charset=utf-8",
             "log": "text/plain; charset=utf-8"}[path.suffix.lower().lstrip(".")]
    return FileResponse(path, media_type=media,
                        headers={"Content-Disposition": f'inline; filename="{path.name}"'})


@router.get("/diagnostics/tail")
async def diagnostics_tail(
    name: str = Query(min_length=1),
    lines: int = Query(default=200, ge=10, le=2000),
) -> dict:
    """Last N lines of a log file — enough to see why a capture failed."""
    path = _safe_diag_path(name)
    if path.suffix.lower() != ".log":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only .log files can be tailed")
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            fh.seek(max(0, fh.tell() - 512 * 1024))
            text = fh.read().decode("utf-8", errors="replace")
    except OSError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Could not read log: {exc}")
    tail = text.splitlines()[-lines:]
    return {"name": path.name, "lines": tail}
