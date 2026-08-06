"""Application configuration loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# repo root = backend/app/core/config.py -> parents[3]
ROOT_DIR = Path(__file__).resolve().parents[3]
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(ROOT_DIR / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Application
    app_name: str = "AIAuto"
    env: str = "production"
    debug: bool = False
    secret_key: str = "change-me-to-a-long-random-string"
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    # Infrastructure
    database_url: str = "sqlite+aiosqlite:///./storage/aiauto.db"
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    access_token_minutes: int = 30
    refresh_token_days: int = 7
    jwt_algorithm: str = "HS256"

    # Storage
    storage_dir: str = "storage"
    upload_dir: str = "storage/uploads"
    results_dir: str = "storage/results"
    backup_dir: str = "backups"
    max_upload_mb: int = 50
    storage_limit_gb: int = 50

    # Queue / jobs
    max_concurrent_jobs: int = 1
    max_queue_size: int = 200
    job_retry_count: int = 2
    job_timeout_seconds: int = 600

    # Rate limiting
    rate_limit_per_minute: int = 60
    login_rate_limit_per_minute: int = 10

    # Worker / automation
    ai_provider: str = "browser"  # "browser" | "api"
    chrome_cdp_url: str = "http://localhost:9222"
    chrome_profile_dir: str = ""
    chrome_headless: bool = False
    chatgpt_url: str = "https://chatgpt.com"
    response_timeout_seconds: int = 480
    delete_conversations_after_run: bool = True
    openai_api_key: str = ""
    openai_text_model: str = "gpt-4o"
    openai_image_model: str = "gpt-image-1"

    # GitHub auto-update
    github_repo: str = ""
    github_branch: str = "main"
    github_token: str = ""
    update_protected_paths: str = (
        ".env,config.php,storage,uploads,backups,logs,frontend/node_modules"
    )
    update_auto_restart: bool = True

    # ---- helpers ----
    @field_validator("database_url")
    @classmethod
    def _anchor_relative_sqlite(cls, v: str) -> str:
        """Anchor relative SQLite paths to the repo root so the app works
        regardless of the process working directory."""
        prefix = "sqlite+aiosqlite:///"
        if v.startswith(prefix):
            raw = v.removeprefix(prefix).lstrip("./")
            first = raw.split("/")[0] if raw else ""
            if raw and not raw.startswith("/") and ":" not in first:  # not abs, not C:\
                path = ROOT_DIR / raw
                path.parent.mkdir(parents=True, exist_ok=True)
                return prefix + str(path)
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def root_dir(self) -> Path:
        return ROOT_DIR

    def _abs(self, p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else ROOT_DIR / path

    @property
    def storage_path(self) -> Path:
        return self._abs(self.storage_dir)

    @property
    def upload_path(self) -> Path:
        return self._abs(self.upload_dir)

    @property
    def results_path(self) -> Path:
        return self._abs(self.results_dir)

    @property
    def backup_path(self) -> Path:
        return self._abs(self.backup_dir)

    @property
    def protected_paths(self) -> list[str]:
        return [p.strip().strip("/") for p in self.update_protected_paths.split(",") if p.strip()]

    def ensure_dirs(self) -> None:
        for p in (self.storage_path, self.upload_path, self.results_path, self.backup_path):
            p.mkdir(parents=True, exist_ok=True)
        (ROOT_DIR / "logs").mkdir(exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
