from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.file import FileKind
from app.models.prompt import PromptStatus


class PromptCreate(BaseModel):
    prompt_text: str = Field(min_length=1, max_length=32000)
    wants_image: bool = False
    priority: int = Field(default=0, ge=0, le=10)
    computer_name: str = Field(default="", max_length=128)
    image_size: str = Field(default="auto", max_length=32)
    parent_id: str | None = Field(default=None, max_length=32)
    is_utility: bool = False


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: FileKind
    filename: str
    mime_type: str
    size_bytes: int
    has_thumbnail: bool = False
    created_at: datetime


class PromptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: int
    prompt_text: str
    response_text: str | None = None
    status: PromptStatus
    priority: int
    wants_image: bool
    image_size: str = "auto"
    parent_id: str | None = None
    error: str | None = None
    retry_count: int
    computer_name: str
    department: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    files: list[FileOut] = []
    user_name: str = ""
    queue_position: int | None = None


class PromptListOut(BaseModel):
    items: list[PromptOut]
    total: int
    page: int
    page_size: int
