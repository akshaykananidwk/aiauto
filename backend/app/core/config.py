"""Application configuration loaded from environment / .env."""
from __future__ import annotations

import os
import secrets as _secrets
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = backend/app/core/config.py -> parents[3].
# AIAUTO_ROOT overrides it for deployments where the package layout
# differs from the repo checkout (e.g. containers).
_env_root = os.environ.get("AIAUTO_ROOT", "")
ROOT_DIR = Path(_env_root).resolve() if _env_root else Path(__file__).resolve().parents[3]
BACKEND_DIR = Path(__file__).resolve().parents[2]

DEFAULT_SECRET = "change-me-to-a-long-random-string"


def ensure_env_file() -> bool:
    """Create .env from .env.example with a generated SECRET_KEY on first
    run. Runs BEFORE Settings loads so the generated key takes effect
    immediately. Returns True if the file was created."""
    env_path = ROOT_DIR / ".env"
    example = ROOT_DIR / ".env.example"
    if env_path.exists() or not example.exists():
        return False
    content = example.read_text(encoding="utf-8").replace(
        f"SECRET_KEY={DEFAULT_SECRET}",
        f"SECRET_KEY={_secrets.token_urlsafe(64)}",
    )
    env_path.write_text(content, encoding="utf-8")
    return True


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
    secret_key: str = DEFAULT_SECRET
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
    ai_provider: str = "browser"  # default provider: browser | openai | anthropic | gemini
    ai_failover_chain: str = ""   # e.g. "browser,openai,anthropic" — empty disables failover
    worker_id: str = ""           # unique per worker machine; auto-generated when empty
    chrome_cdp_url: str = "http://localhost:9222"
    chrome_profile_dir: str = ""
    chrome_headless: bool = False
    chatgpt_url: str = "https://chatgpt.com"
    response_timeout_seconds: int = 480
    delete_conversations_after_run: bool = True
    enable_doc_extraction: bool = True  # extract text from PDF uploads for API providers
    openai_api_key: str = ""
    openai_text_model: str = "gpt-4o"
    openai_image_model: str = "gpt-image-1"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # Quota defaults (0 = unlimited); user/department settings override
    default_daily_limit: int = 0
    default_monthly_limit: int = 0

    # Notifications
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "aiauto@localhost"
    smtp_tls: bool = True
    telegram_bot_token: str = ""
    notify_webhook_url: str = ""  # generic webhook (Slack/WhatsApp gateway/…)

    # Monitoring / maintenance
    disk_alert_percent: int = 90
    backup_schedule_time: str = ""  # "HH:MM" UTC for daily automatic backups; empty = off

    # Auth hardening
    login_max_failures: int = 5
    login_lockout_minutes: int = 15

    # GitHub auto-update
    github_repo: str = ""
    github_branch: str = "main"
    github_token: str = ""
    update_protected_paths: str = (
        ".env,config.php,storage,uploads,backups,logs,plugins,frontend/node_modules"
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
    ensure_env_file()
    return Settings()


def assert_production_ready(settings: Settings) -> None:
    """Refuse to run with the public default SECRET_KEY outside dev/test —
    it would let anyone forge admin JWTs."""
    if settings.secret_key == DEFAULT_SECRET and settings.env not in ("development", "test"):
        raise RuntimeError(
            "SECRET_KEY is still the public default. Set a random value in .env "
            "(python -c \"import secrets; print(secrets.token_urlsafe(64))\") "
            "or delete .env so it is regenerated, then restart."
        )
