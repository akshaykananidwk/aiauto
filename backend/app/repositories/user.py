from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, user_id: int) -> User | None:
        return await self.db.get(User, user_id)

    async def get_by_username(self, username: str) -> User | None:
        res = await self.db.execute(select(User).where(User.username == username))
        return res.scalar_one_or_none()

    async def list(self, include_inactive: bool = True) -> list[User]:
        stmt = select(User).order_by(User.id)
        if not include_inactive:
            stmt = stmt.where(User.is_active.is_(True))
        return list((await self.db.execute(stmt)).scalars().all())

    async def count(self) -> int:
        return (await self.db.execute(select(func.count(User.id)))).scalar_one()

    def add(self, user: User) -> None:
        self.db.add(user)
