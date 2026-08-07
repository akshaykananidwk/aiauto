from __future__ import annotations

from pydantic import BaseModel, Field

from app.services.prompt_builder import DEFAULT_IMAGE_INSTRUCTION


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
    default_daily_limit: int = Field(default=0, ge=0, le=1_000_000)
    default_monthly_limit: int = Field(default=0, ge=0, le=10_000_000)
    announcement: str = Field(default="", max_length=2000)
    # appended (in English) to every "Generate image" prompt before it is
    # sent to the AI — empty disables the feature
    image_prompt_instruction: str = Field(
        default=DEFAULT_IMAGE_INSTRUCTION, max_length=2000)
    # delete result/upload FILES older than N days (prompt text is kept
    # so history stays readable). 0 = never delete anything
    file_retention_days: int = Field(default=0, ge=0, le=3650)
    # answer audio: "offline" = the computer's own voices (nothing leaves
    # the network), "online" = Google TTS (better Gujarati/Hindi, but the
    # answer text is sent to Google), "off" = no audio downloads
    tts_engine: str = Field(default="offline", pattern="^(offline|online|off)$")
    tts_language: str = Field(default="en", max_length=8)


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
    default_daily_limit: int | None = Field(default=None, ge=0, le=1_000_000)
    default_monthly_limit: int | None = Field(default=None, ge=0, le=10_000_000)
    announcement: str | None = Field(default=None, max_length=2000)
    image_prompt_instruction: str | None = Field(default=None, max_length=2000)
    file_retention_days: int | None = Field(default=None, ge=0, le=3650)
    tts_engine: str | None = Field(default=None, pattern="^(offline|online|off)$")
    tts_language: str | None = Field(default=None, max_length=8)
