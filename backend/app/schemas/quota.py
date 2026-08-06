from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DepartmentQuotaIn(BaseModel):
    department: str = Field(min_length=1, max_length=128)
    daily_limit: int = Field(default=0, ge=0, le=1_000_000)
    monthly_limit: int = Field(default=0, ge=0, le=10_000_000)


class DepartmentQuotaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    department: str
    daily_limit: int
    monthly_limit: int
    updated_at: datetime


class QuotaUsageOut(BaseModel):
    daily_used: int
    daily_limit: int
    monthly_used: int
    monthly_limit: int
