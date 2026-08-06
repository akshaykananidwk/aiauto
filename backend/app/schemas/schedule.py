from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.schedule import ScheduleType


class ScheduleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    prompt_text: str = Field(min_length=1, max_length=32000)
    wants_image: bool = False
    provider: str = Field(default="", max_length=32)
    schedule_type: ScheduleType
    interval_minutes: int | None = Field(default=None, ge=5, le=10080)
    run_at_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    weekday: int | None = Field(default=None, ge=0, le=6)
    run_once_at: datetime | None = None  # for schedule_type=once

    @field_validator("run_at_time")
    @classmethod
    def _valid_time(cls, v: str | None) -> str | None:
        if v is not None:
            hour, minute = (int(x) for x in v.split(":"))
            if hour > 23 or minute > 59:
                raise ValueError("invalid time")
        return v


class ScheduleUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    prompt_text: str | None = Field(default=None, min_length=1, max_length=32000)
    is_active: bool | None = None
    interval_minutes: int | None = Field(default=None, ge=5, le=10080)
    run_at_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    weekday: int | None = Field(default=None, ge=0, le=6)


class ScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    prompt_text: str
    wants_image: bool
    provider: str
    schedule_type: ScheduleType
    interval_minutes: int | None = None
    run_at_time: str | None = None
    weekday: int | None = None
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_prompt_id: str | None = None
    is_active: bool
    created_at: datetime
