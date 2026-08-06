"""Background scheduler running inside the API server.

Every tick (30 s) it:
  * launches due scheduled prompts,
  * re-queues orphaned jobs (waiting in DB but missing from Redis, or
    stuck "processing" with no live worker owning them → automatic
    failover when a worker dies mid-job),
  * checks disk usage and alerts admins past the threshold,
  * runs the daily automatic backup at the configured time.

A Redis lock ensures only one process runs the tick when several API
workers are deployed.
"""
from __future__ import annotations

import asyncio
import contextlib
import shutil
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import async_session_factory
from app.models.prompt import Prompt, PromptStatus
from app.models.schedule import ScheduledPrompt, ScheduleType
from app.services import events
from app.services.audit import audit
from app.services.notify import NotificationService
from app.services.queue import QueueService
from app.services.redis_client import get_redis

logger = get_logger("scheduler")

LOCK_KEY = "aiauto:scheduler:lock"
TICK_SECONDS = 30
DISK_ALERT_KEY = "aiauto:scheduler:disk_alerted"
BACKUP_MARK_KEY = "aiauto:scheduler:last_backup_day"


def compute_next_run(
    schedule_type: ScheduleType,
    *,
    now: datetime,
    interval_minutes: int | None = None,
    run_at_time: str | None = None,
    weekday: int | None = None,
) -> datetime | None:
    """Pure function: next UTC run time for a schedule (None for finished
    one-shot schedules)."""
    if schedule_type == ScheduleType.once:
        return None
    if schedule_type == ScheduleType.interval:
        minutes = max(1, interval_minutes or 60)
        return now + timedelta(minutes=minutes)
    hour, minute = 9, 0
    if run_at_time and ":" in run_at_time:
        try:
            hour, minute = (int(x) for x in run_at_time.split(":", 1))
        except ValueError:
            pass
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if schedule_type == ScheduleType.daily:
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate
    # weekly
    target = weekday if weekday is not None else 0
    days_ahead = (target - candidate.weekday()) % 7
    candidate += timedelta(days=days_ahead)
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


class SchedulerService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                redis = get_redis()
                # single-runner lock across API processes
                if await redis.set(LOCK_KEY, "1", nx=True, ex=TICK_SECONDS - 2):
                    async with async_session_factory() as db:
                        await self._run_due_schedules(db)
                        await self._requeue_orphans(db)
                        await self._check_disk(db)
                        await self._maybe_backup(db)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.exception("scheduler tick failed: %s", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=TICK_SECONDS)
            except asyncio.TimeoutError:
                pass

    # ---- scheduled prompts ----

    async def _run_due_schedules(self, db: AsyncSession) -> None:
        now = datetime.now(timezone.utc)
        res = await db.execute(
            select(ScheduledPrompt.id).where(
                ScheduledPrompt.is_active.is_(True),
                ScheduledPrompt.next_run_at.isnot(None),
                ScheduledPrompt.next_run_at <= now,
            )
        )
        # iterate over ids and re-fetch inside the loop: a rollback for one
        # schedule must not leave expired instances for the next iteration
        for sched_id in res.scalars().all():
            sched = await db.get(ScheduledPrompt, sched_id)
            if sched is None or not sched.is_active:
                continue
            try:
                from app.models.user import User

                user = await db.get(User, sched.user_id)
                if user is None or not user.is_active:
                    sched.is_active = False
                    continue
                prompt = Prompt(
                    user_id=user.id,
                    prompt_text=sched.prompt_text,
                    wants_image=sched.wants_image,
                    department=user.department,
                    computer_name="scheduler",
                    scheduled_id=sched.id,
                )
                db.add(prompt)
                await db.flush()
                sched.last_run_at = now
                sched.last_prompt_id = prompt.id
                sched.next_run_at = compute_next_run(
                    sched.schedule_type,
                    now=now,
                    interval_minutes=sched.interval_minutes,
                    run_at_time=sched.run_at_time,
                    weekday=sched.weekday,
                )
                if sched.next_run_at is None:
                    sched.is_active = False
                await audit(db, "schedule.fired",
                            f"scheduled prompt '{sched.title}' fired -> {prompt.id}",
                            user_id=user.id, meta={"schedule_id": sched.id})
                await db.commit()
                await QueueService().enqueue(prompt.id, prompt.priority)
                await events.publish(events.PROMPT_SUBMITTED,
                                     {"prompt_id": prompt.id, "scheduled": True},
                                     user_id=user.id)
            except Exception as exc:
                logger.error("scheduled prompt %s failed to fire: %s", sched.id, exc)
                await db.rollback()

    # ---- failover / orphan recovery ----

    async def _requeue_orphans(self, db: AsyncSession) -> None:
        queue = QueueService()
        redis = get_redis()
        try:
            active = await queue.active_job_ids()
        except Exception:
            return  # Redis unavailable — nothing to reconcile

        # Waiting in DB but not queued anywhere → lost enqueue. A prompt is
        # only re-added after being missing on TWO consecutive ticks (redis
        # marker), because a just-popped job is legitimately absent from the
        # queue for a few seconds before the worker commits `processing` or
        # its heartbeat advertises the job — created_at age proves nothing.
        res = await db.execute(
            select(Prompt).where(Prompt.status == PromptStatus.waiting).limit(500)
        )
        for prompt in res.scalars().all():
            marker = f"aiauto:orphan:{prompt.id}"
            try:
                if await queue.in_queue(prompt.id) or prompt.id in active:
                    await redis.delete(marker)
                    continue
                first_sighting = await redis.set(marker, "1", nx=True, ex=600)
                if first_sighting:
                    continue  # give it one full tick to reappear
                await redis.delete(marker)
                await queue.enqueue(prompt.id, prompt.priority)
                logger.warning("re-queued orphaned waiting prompt %s", prompt.id)
            except Exception as exc:
                logger.warning("orphan check failed for %s: %s", prompt.id, exc)

        # processing but no live worker owns it → the worker died mid-job
        stale_after = timedelta(seconds=self.settings.job_timeout_seconds + 120)
        res = await db.execute(
            select(Prompt).where(Prompt.status == PromptStatus.processing)
        )
        changed = False
        for prompt in res.scalars().all():
            if prompt.id in active:
                continue
            started = prompt.started_at or prompt.created_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - started < stale_after:
                continue
            if prompt.retry_count < self.settings.job_retry_count:
                prompt.retry_count += 1
                prompt.status = PromptStatus.waiting
                prompt.error = "worker lost mid-job — automatically re-queued"
                await queue.enqueue(prompt.id, prompt.priority)
            else:
                prompt.status = PromptStatus.failed
                prompt.error = "worker lost mid-job and retry limit reached"
                prompt.completed_at = datetime.now(timezone.utc)
                await events.publish(events.PROMPT_FAILED,
                                     {"prompt_id": prompt.id, "error": prompt.error},
                                     user_id=prompt.user_id)
            await audit(db, "queue.failover", f"recovered stale job {prompt.id}",
                        level="warning", meta={"prompt_id": prompt.id})
            changed = True
        if changed:
            await db.commit()

    # ---- disk alert ----

    async def _check_disk(self, db: AsyncSession) -> None:
        total, used, _free = shutil.disk_usage(self.settings.root_dir)
        percent = used / total * 100
        redis = get_redis()
        if percent >= self.settings.disk_alert_percent:
            # alert at most once per 6 hours
            if await redis.set(DISK_ALERT_KEY, "1", nx=True, ex=6 * 3600):
                await NotificationService(db).notify_admins(
                    "warning", "Disk usage alert",
                    f"Disk is {percent:.0f}% full "
                    f"(threshold {self.settings.disk_alert_percent}%). "
                    "Free space or raise storage limits.",
                )
                await db.commit()

    # ---- automatic daily backup ----

    async def _maybe_backup(self, db: AsyncSession) -> None:
        at = self.settings.backup_schedule_time
        if not at or ":" not in at:
            return
        now = datetime.now(timezone.utc)
        try:
            hour, minute = (int(x) for x in at.split(":", 1))
        except ValueError:
            return
        if (now.hour, now.minute) < (hour, minute):
            return
        redis = get_redis()
        today = now.strftime("%Y-%m-%d")
        if await redis.get(BACKUP_MARK_KEY) == today:
            return
        await redis.set(BACKUP_MARK_KEY, today)
        try:
            from app.services.system import SystemService

            result = await SystemService(db).create_backup()
            await audit(db, "backup.scheduled", f"automatic backup: {result['backup']}",
                        commit=True)
        except Exception as exc:
            logger.error("scheduled backup failed: %s", exc)


scheduler = SchedulerService()
