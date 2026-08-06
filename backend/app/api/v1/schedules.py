"""Scheduled prompts (workflow automation)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.schedule import ScheduledPrompt, ScheduleType
from app.models.user import User, UserRole
from app.schemas.schedule import ScheduleCreate, ScheduleOut, ScheduleUpdate
from app.services.audit import audit
from app.services.scheduler import compute_next_run

router = APIRouter(prefix="/schedules", tags=["schedules"])


def _initial_next_run(body: ScheduleCreate) -> datetime | None:
    now = datetime.now(timezone.utc)
    if body.schedule_type == ScheduleType.once:
        run_at = body.run_once_at
        if run_at is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "run_once_at is required for one-time schedules")
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=timezone.utc)
        if run_at <= now:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "run_once_at must be in the future")
        return run_at
    if body.schedule_type == ScheduleType.interval and not body.interval_minutes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "interval_minutes is required for interval schedules")
    if body.schedule_type in (ScheduleType.daily, ScheduleType.weekly) and not body.run_at_time:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "run_at_time (HH:MM UTC) is required for daily/weekly schedules")
    return compute_next_run(
        body.schedule_type, now=now, interval_minutes=body.interval_minutes,
        run_at_time=body.run_at_time, weekday=body.weekday,
    )


@router.get("", response_model=list[ScheduleOut])
async def list_schedules(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[ScheduledPrompt]:
    stmt = select(ScheduledPrompt).order_by(ScheduledPrompt.created_at.desc())
    if user.role != UserRole.admin:
        stmt = stmt.where(ScheduledPrompt.user_id == user.id)
    return list((await db.execute(stmt)).scalars().all())


@router.post("", response_model=ScheduleOut, status_code=201)
async def create_schedule(
    body: ScheduleCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScheduledPrompt:
    sched = ScheduledPrompt(
        user_id=user.id,
        title=body.title,
        prompt_text=body.prompt_text,
        wants_image=body.wants_image,
        provider=body.provider,
        schedule_type=body.schedule_type,
        interval_minutes=body.interval_minutes,
        run_at_time=body.run_at_time,
        weekday=body.weekday,
        next_run_at=_initial_next_run(body),
    )
    db.add(sched)
    await audit(db, "schedule.created", f"schedule '{body.title}' created", user_id=user.id)
    await db.commit()
    await db.refresh(sched)
    return sched


async def _get_own_schedule(schedule_id: int, user: User, db: AsyncSession) -> ScheduledPrompt:
    sched = await db.get(ScheduledPrompt, schedule_id)
    if sched is None or (user.role != UserRole.admin and sched.user_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Schedule not found")
    return sched


@router.patch("/{schedule_id}", response_model=ScheduleOut)
async def update_schedule(
    schedule_id: int,
    body: ScheduleUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScheduledPrompt:
    sched = await _get_own_schedule(schedule_id, user, db)
    patch = body.model_dump(exclude_none=True)
    reactivated = patch.get("is_active") and not sched.is_active
    for key, value in patch.items():
        setattr(sched, key, value)
    if {"interval_minutes", "run_at_time", "weekday"} & patch.keys() or reactivated:
        sched.next_run_at = compute_next_run(
            sched.schedule_type, now=datetime.now(timezone.utc),
            interval_minutes=sched.interval_minutes,
            run_at_time=sched.run_at_time, weekday=sched.weekday,
        )
    await db.commit()
    await db.refresh(sched)
    return sched


@router.delete("/{schedule_id}")
async def delete_schedule(
    schedule_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sched = await _get_own_schedule(schedule_id, user, db)
    await db.delete(sched)
    await db.commit()
    return {"ok": True}
