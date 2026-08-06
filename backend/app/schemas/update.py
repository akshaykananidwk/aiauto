from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.update import UpdateStatus


class UpdateConfigOut(BaseModel):
    repo: str = ""
    branch: str = "main"
    token_set: bool = False
    protected_paths: list[str] = []
    auto_restart: bool = True
    current_commit: str = ""
    current_version: str = ""


class UpdateConfigIn(BaseModel):
    repo: str = Field(pattern=r"^[\w.-]+/[\w.-]+$", description="owner/repo")
    branch: str = Field(default="main", min_length=1, max_length=100)
    # Empty string = keep the existing stored token
    token: str = Field(default="", max_length=255)
    protected_paths: list[str] | None = None
    auto_restart: bool | None = None


class CommitInfo(BaseModel):
    sha: str
    message: str
    author: str
    date: str


class UpdateCheckOut(BaseModel):
    update_available: bool
    current_commit: str = ""
    current_version: str = ""
    latest_commit: str = ""
    latest_version: str = ""
    commits_behind: int = 0
    commits: list[CommitInfo] = []


class UpdateRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_commit: str
    to_commit: str
    version: str
    status: UpdateStatus
    log: str
    backup_path: str
    created_at: datetime
    finished_at: datetime | None = None


class UpdateRunStatus(BaseModel):
    running: bool
    step: str = ""
    progress: int = 0
    log_tail: list[str] = []
