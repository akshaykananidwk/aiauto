"""Admin endpoints for the one-click GitHub update system."""
from __future__ import annotations

import asyncio

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.core.logging import get_logger
from app.db.session import async_session_factory, get_db
from app.models.update import UpdateRecord
from app.models.user import User
from app.schemas.update import (
    UpdateCheckOut,
    UpdateConfigIn,
    UpdateConfigOut,
    UpdateRecordOut,
    UpdateRunStatus,
)
from app.services.audit import audit
from app.services.update import UpdateService, run_state

logger = get_logger("api.updates")

router = APIRouter(prefix="/admin/update", tags=["updates"],
                   dependencies=[Depends(get_current_admin)])


@router.get("/config", response_model=UpdateConfigOut)
async def get_update_config(db: AsyncSession = Depends(get_db)) -> UpdateConfigOut:
    svc = UpdateService(db)
    cfg = await svc.get_config()
    return UpdateConfigOut(
        repo=cfg["repo"],
        branch=cfg["branch"],
        token_set=bool(cfg["token"]),
        protected_paths=cfg["protected_paths"],
        auto_restart=cfg["auto_restart"],
        current_commit=cfg["current_commit"],
        current_version=svc.current_version(),
    )


@router.put("/config", response_model=UpdateConfigOut)
async def save_update_config(
    body: UpdateConfigIn,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> UpdateConfigOut:
    svc = UpdateService(db)
    await svc.save_config(body.repo, body.branch, body.token, body.protected_paths,
                          body.auto_restart)
    await audit(db, "update.config_saved", f"update config saved ({body.repo}@{body.branch})",
                user_id=admin.id, commit=True)
    return await get_update_config(db)


@router.post("/check", response_model=UpdateCheckOut)
async def check_for_update(
    admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> UpdateCheckOut:
    svc = UpdateService(db)
    try:
        result = await svc.check()
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    except httpx.HTTPStatusError as exc:
        detail = f"GitHub API error {exc.response.status_code}"
        if exc.response.status_code in (401, 403):
            detail += " — check the GitHub token"
        elif exc.response.status_code == 404:
            detail += " — repository or branch not found (or token lacks access)"
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail)
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"GitHub unreachable: {exc}")
    await audit(db, "update.checked",
                f"update check: available={result['update_available']}",
                user_id=admin.id, commit=True)
    return UpdateCheckOut(**result)


async def _run_update_background() -> None:
    """Run the update pipeline with its own DB session (survives the request)."""
    async with async_session_factory() as db:
        try:
            await UpdateService(db).run_update()
        except Exception as exc:
            logger.error("background update finished with error: %s", exc)


@router.post("/run", status_code=202)
async def run_update_now(
    admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
):
    if run_state()["running"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "An update is already running")
    cfg = await UpdateService(db).get_config()
    if not cfg["repo"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Update not configured")
    await audit(db, "update.started", "one-click update started", user_id=admin.id, commit=True)
    asyncio.get_running_loop().create_task(_run_update_background())
    return {"started": True}


@router.get("/status", response_model=UpdateRunStatus)
async def update_status() -> UpdateRunStatus:
    return UpdateRunStatus(**run_state())


@router.get("/history", response_model=list[UpdateRecordOut])
async def update_history(db: AsyncSession = Depends(get_db)) -> list[UpdateRecord]:
    res = await db.execute(
        select(UpdateRecord).order_by(UpdateRecord.created_at.desc()).limit(50)
    )
    return list(res.scalars().all())
