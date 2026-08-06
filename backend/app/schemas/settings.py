from __future__ import annotations

from pydantic import BaseModel, Field


class AdminSettings(BaseModel):
    """Runtime-configurable settings, stored in the app_settings table."""

    max_concurrent_jobs: int = Field(default=1, ge=1, le=10)
    max_queue_size: int = Field(default=200, ge=1, le=10000)
    job_retry_count: int = Field(default=2, ge=0, le=10)
    job_timeout_seconds: int = Field(default=600, ge=30, le=3600)
    response_timeout_seconds: int = Field(default=480, ge=30, le=3600)
    storage_limit_gb: int = Field(default=50, ge=1, le=10000)
    download_dir: str = Field(default="storage/results", max_length=512)
    browser_profile_path: str = Field(default="", max_length=512)
    delete_conversations_after_run: bool = True
    backup_keep_count: int = Field(default=10, ge=1, le=100)


class AdminSettingsUpdate(BaseModel):
    max_concurrent_jobs: int | None = Field(default=None, ge=1, le=10)
    max_queue_size: int | None = Field(default=None, ge=1, le=10000)
    job_retry_count: int | None = Field(default=None, ge=0, le=10)
    job_timeout_seconds: int | None = Field(default=None, ge=30, le=3600)
    response_timeout_seconds: int | None = Field(default=None, ge=30, le=3600)
    storage_limit_gb: int | None = Field(default=None, ge=1, le=10000)
    download_dir: str | None = None
    browser_profile_path: str | None = None
    delete_conversations_after_run: bool | None = None
    backup_keep_count: int | None = Field(default=None, ge=1, le=100)
