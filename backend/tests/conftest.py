"""Shared test fixtures: isolated SQLite DB, fakeredis, ASGI test client."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="aiauto-test-"))
os.environ.update({
    "ENV": "test",
    "SECRET_KEY": "test-secret-key-for-tests-only-not-production",
    "DATABASE_URL": f"sqlite+aiosqlite:///{_TMP}/test.db",
    "REDIS_URL": "redis://127.0.0.1:1/9",  # never dialled — fakeredis is injected
    "STORAGE_DIR": str(_TMP / "storage"),
    "UPLOAD_DIR": str(_TMP / "storage/uploads"),
    "RESULTS_DIR": str(_TMP / "storage/results"),
    "BACKUP_DIR": str(_TMP / "backups"),
    "RATE_LIMIT_PER_MINUTE": "100000",
    "LOGIN_RATE_LIMIT_PER_MINUTE": "100000",
    "LOGIN_MAX_FAILURES": "3",
    "LOGIN_LOCKOUT_MINUTES": "1",
    "DEFAULT_DAILY_LIMIT": "0",
    "DEFAULT_MONTHLY_LIMIT": "0",
    "GITHUB_REPO": "",
    "GITHUB_TOKEN": "",
    "AI_PROVIDER": "browser",
})

import fakeredis.aioredis  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

import app.services.redis_client as redis_client_module  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.session import async_session_factory, init_db  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_client_module, "_client", fake)
    yield fake


@pytest_asyncio.fixture
async def db():
    await init_db()
    async with async_session_factory() as session:
        yield session


async def _ensure_user(username: str, role: UserRole, department: str = "") -> None:
    async with async_session_factory() as session:
        from sqlalchemy import select

        existing = (
            await session.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()
        if existing is None:
            session.add(User(
                username=username,
                full_name=username.title(),
                department=department,
                role=role,
                hashed_password=hash_password("password123"),
            ))
        else:
            # reset any per-test changes (limits, active flag)
            existing.is_active = True
            existing.daily_limit = None
            existing.monthly_limit = None
        await session.commit()


@pytest_asyncio.fixture
async def client():
    await init_db()
    await _ensure_user("admin", UserRole.admin)
    await _ensure_user("alice", UserRole.staff, "Sales")
    await _ensure_user("bob", UserRole.staff, "Support")
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def login(client: AsyncClient, username: str, password: str = "password123") -> dict:
    res = await client.post("/api/v1/auth/login",
                            json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return res.json()


async def auth_headers(client: AsyncClient, username: str) -> dict:
    tokens = await login(client, username)
    return {"Authorization": f"Bearer {tokens['access_token']}"}
