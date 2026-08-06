from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    prefix: str
    is_active: bool
    last_used_at: datetime | None = None
    created_at: datetime


class ApiKeyCreated(ApiKeyOut):
    # the full key — returned exactly once at creation
    plain_key: str
