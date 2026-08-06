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
