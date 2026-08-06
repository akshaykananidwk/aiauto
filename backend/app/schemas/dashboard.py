from __future__ import annotations

from pydantic import BaseModel


class QueueStats(BaseModel):
    waiting: int = 0
    processing: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0


class UsageStats(BaseModel):
    today: int = 0
    week: int = 0
    month: int = 0


class WorkerStatus(BaseModel):
    worker_online: bool = False
    chrome_connected: bool = False
    playwright_ready: bool = False
    last_heartbeat: str | None = None


class AdminDashboard(BaseModel):
    queue: QueueStats
    usage: UsageStats
    total_users: int = 0
    total_prompts: int = 0
    image_count: int = 0
    file_count: int = 0
    storage_used_mb: float = 0
    worker: WorkerStatus


class StaffDashboard(BaseModel):
    my_queue: QueueStats
    my_usage: UsageStats
