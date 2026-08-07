"""Usage analytics: time series, per-user/department breakdowns, and
processing-time statistics for the central ChatGPT automation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import Float, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import FileKind, PromptFile
from app.models.prompt import Prompt, PromptStatus
from app.models.user import User


class AnalyticsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def daily_series(self, days: int = 30) -> list[dict]:
        """Prompts per calendar day (UTC) for the last N days."""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        day = func.date(Prompt.created_at)
        stmt = (
            select(day.label("day"), func.count(Prompt.id))
            .where(Prompt.created_at >= since)
            .group_by(day)
            .order_by(day)
        )
        rows = (await self.db.execute(stmt)).all()
        by_day = {str(d): c for d, c in rows}
        out = []
        today = datetime.now(timezone.utc).date()
        for offset in range(days - 1, -1, -1):
            key = str(today - timedelta(days=offset))
            out.append({"day": key, "count": by_day.get(key, 0)})
        return out

    async def top_users(self, days: int = 30, limit: int = 10) -> list[dict]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(
                User.username,
                User.full_name,
                User.department,
                func.count(Prompt.id).label("prompts"),
            )
            .join(Prompt, Prompt.user_id == User.id)
            .where(Prompt.created_at >= since)
            .group_by(User.id)
            .order_by(func.count(Prompt.id).desc())
            .limit(limit)
        )
        return [
            {
                "username": r.username,
                "full_name": r.full_name,
                "department": r.department,
                "prompts": r.prompts,
            }
            for r in (await self.db.execute(stmt)).all()
        ]

    async def by_department(self, days: int = 30) -> list[dict]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(Prompt.department, func.count(Prompt.id))
            .where(Prompt.created_at >= since)
            .group_by(Prompt.department)
            .order_by(func.count(Prompt.id).desc())
        )
        return [
            {"department": d or "(none)", "prompts": c}
            for d, c in (await self.db.execute(stmt)).all()
        ]

    async def timing(self, days: int = 30, sample_cap: int = 5000) -> dict:
        """Processing-time statistics + busiest hours.

        Computed in Python over a bounded sample so it works identically on
        SQLite and PostgreSQL (SQLite has no extract(epoch)).
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)
        rows = (await self.db.execute(
            select(Prompt.started_at, Prompt.completed_at, Prompt.created_at,
                   Prompt.status, Prompt.wants_image)
            .where(Prompt.created_at >= since, Prompt.is_utility.is_(False))
            .order_by(Prompt.created_at.desc())
            .limit(sample_cap)
        )).all()

        def seconds(a, b) -> float | None:
            if a is None or b is None:
                return None
            delta = (b - a).total_seconds()
            return delta if delta >= 0 else None

        run_image: list[float] = []
        run_text: list[float] = []
        waits: list[float] = []
        by_hour = [0] * 24
        done = failed = 0
        for started, completed, created, status, wants_image in rows:
            if created is not None:
                by_hour[created.hour] += 1
            if status == PromptStatus.completed:
                done += 1
            elif status == PromptStatus.failed:
                failed += 1
            wait = seconds(created, started)
            if wait is not None:
                waits.append(wait)
            run = seconds(started, completed)
            if run is not None and status == PromptStatus.completed:
                (run_image if wants_image else run_text).append(run)

        def stats(values: list[float]) -> dict:
            if not values:
                return {"count": 0, "avg": None, "median": None,
                        "fastest": None, "slowest": None}
            ordered = sorted(values)
            mid = len(ordered) // 2
            median = (ordered[mid] if len(ordered) % 2
                      else (ordered[mid - 1] + ordered[mid]) / 2)
            return {
                "count": len(ordered),
                "avg": round(sum(ordered) / len(ordered), 1),
                "median": round(median, 1),
                "fastest": round(ordered[0], 1),
                "slowest": round(ordered[-1], 1),
            }

        finished = done + failed
        return {
            "images": stats(run_image),
            "text": stats(run_text),
            "queue_wait": stats(waits),
            "by_hour": [{"hour": h, "count": c} for h, c in enumerate(by_hour)],
            "success_rate": round(done / finished * 100, 1) if finished else None,
            "completed": done,
            "failed": failed,
            "sampled": len(rows),
        }

    async def totals(self, days: int = 30) -> dict:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        count = (
            await self.db.execute(
                select(func.count(Prompt.id)).where(Prompt.created_at >= since)
            )
        ).scalar_one()
        images = (
            await self.db.execute(
                select(func.count(PromptFile.id))
                .join(Prompt, PromptFile.prompt_id == Prompt.id)
                .where(Prompt.created_at >= since,
                       PromptFile.kind == FileKind.result_image)
            )
        ).scalar_one()

        # average processing seconds for completed prompts
        secs = func.avg(
            cast(func.extract("epoch", Prompt.completed_at) -
                 func.extract("epoch", Prompt.started_at), Float)
        )
        try:
            avg_secs = (
                await self.db.execute(
                    select(secs).where(
                        Prompt.status == PromptStatus.completed,
                        Prompt.created_at >= since,
                        Prompt.started_at.isnot(None),
                        Prompt.completed_at.isnot(None),
                    )
                )
            ).scalar()
        except Exception:  # SQLite has no extract(epoch)
            avg_secs = None
        return {
            "prompts": count or 0,
            "images": images or 0,
            "avg_processing_seconds": round(float(avg_secs), 1) if avg_secs else None,
        }
