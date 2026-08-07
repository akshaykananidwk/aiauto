from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import FileKind, PromptFile
from app.models.prompt import Prompt, PromptStatus


class PromptRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, prompt_id: str) -> Prompt | None:
        return await self.db.get(Prompt, prompt_id)

    async def list(
        self,
        *,
        user_id: int | None = None,
        status: PromptStatus | None = None,
        search: str | None = None,
        wants_image: bool | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        include_utility: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Prompt], int]:
        stmt = select(Prompt)
        count_stmt = select(func.count(Prompt.id))
        if not include_utility:
            # internal helper jobs (prompt improvement) never show in history
            stmt = stmt.where(Prompt.is_utility.is_(False))
            count_stmt = count_stmt.where(Prompt.is_utility.is_(False))
        if user_id is not None:
            stmt = stmt.where(Prompt.user_id == user_id)
            count_stmt = count_stmt.where(Prompt.user_id == user_id)
        if status is not None:
            stmt = stmt.where(Prompt.status == status)
            count_stmt = count_stmt.where(Prompt.status == status)
        if wants_image is not None:
            stmt = stmt.where(Prompt.wants_image.is_(wants_image))
            count_stmt = count_stmt.where(Prompt.wants_image.is_(wants_image))
        if search:
            # full-text: the request AND the answer, so results can be found
            # by something the AI wrote too
            like = f"%{search}%"
            match = Prompt.prompt_text.ilike(like) | Prompt.response_text.ilike(like)
            stmt = stmt.where(match)
            count_stmt = count_stmt.where(match)
        if created_after is not None:
            stmt = stmt.where(Prompt.created_at >= created_after)
            count_stmt = count_stmt.where(Prompt.created_at >= created_after)
        if created_before is not None:
            stmt = stmt.where(Prompt.created_at <= created_before)
            count_stmt = count_stmt.where(Prompt.created_at <= created_before)
        stmt = (
            stmt.order_by(Prompt.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list((await self.db.execute(stmt)).scalars().unique().all())
        total = (await self.db.execute(count_stmt)).scalar_one()
        return items, total

    async def status_counts(self, user_id: int | None = None) -> dict[str, int]:
        stmt = select(Prompt.status, func.count(Prompt.id)).group_by(Prompt.status)
        if user_id is not None:
            stmt = stmt.where(Prompt.user_id == user_id)
        rows = (await self.db.execute(stmt)).all()
        return {status.value: count for status, count in rows}

    async def usage_counts(self, user_id: int | None = None) -> dict[str, int]:
        now = datetime.now(timezone.utc)
        out: dict[str, int] = {}
        for name, delta in (
            ("today", timedelta(days=1)),
            ("week", timedelta(days=7)),
            ("month", timedelta(days=30)),
        ):
            stmt = select(func.count(Prompt.id)).where(Prompt.created_at >= now - delta)
            if user_id is not None:
                stmt = stmt.where(Prompt.user_id == user_id)
            out[name] = (await self.db.execute(stmt)).scalar_one()
        return out

    async def total(self) -> int:
        return (await self.db.execute(select(func.count(Prompt.id)))).scalar_one()

    async def file_counts(self) -> dict[str, int]:
        stmt = select(PromptFile.kind, func.count(PromptFile.id)).group_by(PromptFile.kind)
        rows = (await self.db.execute(stmt)).all()
        counts = {kind.value: count for kind, count in rows}
        return {
            "images": counts.get(FileKind.result_image.value, 0),
            "files": counts.get(FileKind.result_file.value, 0)
            + counts.get(FileKind.upload.value, 0),
        }

    async def waiting_before(self, prompt: Prompt) -> int:
        """Number of waiting prompts queued ahead of this one (FIFO within priority)."""
        stmt = select(func.count(Prompt.id)).where(
            Prompt.status == PromptStatus.waiting,
            (Prompt.priority > prompt.priority)
            | ((Prompt.priority == prompt.priority) & (Prompt.created_at < prompt.created_at)),
        )
        return (await self.db.execute(stmt)).scalar_one()

    def add(self, prompt: Prompt) -> None:
        self.db.add(prompt)
