from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TemplateCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=32000)
    category: str = Field(default="", max_length=64)
    tags: list[str] = Field(default_factory=list, max_length=20)
    is_shared: bool = False


class TemplateUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=32000)
    category: str | None = Field(default=None, max_length=64)
    tags: list[str] | None = Field(default=None, max_length=20)
    is_shared: bool | None = None


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    title: str
    body: str
    category: str
    tags: list[str] | None = None
    is_shared: bool
    usage_count: int
    created_at: datetime
    updated_at: datetime
    is_favorite: bool = False
    owner_name: str = ""
