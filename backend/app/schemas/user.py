from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class UserBase(BaseModel):
    username: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: EmailStr | None = None
    full_name: str = Field(default="", max_length=128)
    department: str = Field(default="", max_length=128)
    role: UserRole = UserRole.staff


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = None
    department: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    daily_limit: int | None = Field(default=None, ge=0, le=1_000_000)
    monthly_limit: int | None = Field(default=None, ge=0, le=10_000_000)
    telegram_chat_id: str | None = Field(default=None, max_length=64)


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None
    daily_limit: int | None = None
    monthly_limit: int | None = None
    telegram_chat_id: str | None = None
