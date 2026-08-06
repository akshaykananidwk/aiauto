from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.prompt import PromptRepository
from app.repositories.user import UserRepository
from app.schemas.dashboard import (
    AdminDashboard,
    QueueStats,
    StaffDashboard,
    UsageStats,
    WorkerStatus,
)
from app.services.queue import QueueService
from app.services.storage import StorageService


class DashboardService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.prompts = PromptRepository(db)
        self.users = UserRepository(db)
        self.queue = QueueService()

    async def admin(self) -> AdminDashboard:
        status_counts = await self.prompts.status_counts()
        usage = await self.prompts.usage_counts()
        files = await self.prompts.file_counts()
        worker = await self.queue.worker_status()
        storage_used = await StorageService().used_bytes_cached()
        return AdminDashboard(
            queue=QueueStats(**status_counts),
            usage=UsageStats(**usage),
            total_users=await self.users.count(),
            total_prompts=await self.prompts.total(),
            image_count=files["images"],
            file_count=files["files"],
            storage_used_mb=round(storage_used / 1024 / 1024, 1),
            worker=WorkerStatus(
                worker_online=worker["worker_online"],
                chrome_connected=worker["chrome_connected"],
                playwright_ready=worker["playwright_ready"],
                last_heartbeat=worker["last_heartbeat"],
            ),
        )

    async def staff(self, user_id: int) -> StaffDashboard:
        return StaffDashboard(
            my_queue=QueueStats(**await self.prompts.status_counts(user_id)),
            my_usage=UsageStats(**await self.prompts.usage_counts(user_id)),
        )
