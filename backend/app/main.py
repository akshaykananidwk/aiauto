"""AIAuto — Central AI Automation Platform (API server)."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import ROOT_DIR, assert_production_ready, get_settings
from app.core.logging import get_logger, setup_logging
from app.core.rate_limit import RateLimitMiddleware, SecurityHeadersMiddleware
from app.db.session import init_db
from app.services.plugins import load_plugins
from app.services.redis_client import close_redis, get_redis
from app.services.scheduler import scheduler
from app.ws.manager import manager

logger = get_logger("main")
# get_settings() auto-creates .env (with a generated SECRET_KEY) on first run
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    assert_production_ready(settings)
    settings.ensure_dirs()
    await init_db()
    load_plugins()
    manager.start()
    scheduler.start()
    logger.info("%s started (env=%s)", settings.app_name, settings.env)
    yield
    await scheduler.stop()
    await manager.stop()
    await close_redis()
    logger.info("shutdown complete")


app = FastAPI(
    title=settings.app_name,
    version="1.1.0",
    description="Central AI automation platform: staff submit prompts, a queue "
    "dispatches them to AI providers (a managed ChatGPT session or official "
    "APIs), and results (text, images, files) come back — without staff ever "
    "touching the account.",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/api/health")
async def health() -> dict:
    """Liveness + dependency health, used by the start script and monitors."""
    db_ok = redis_ok = False
    try:
        from app.db.session import async_session_factory

        async with async_session_factory() as db:
            await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass
    try:
        redis_ok = bool(await get_redis().ping())
    except Exception:
        pass
    status = "ok" if (db_ok and redis_ok) else "degraded"
    return {"status": status, "app": settings.app_name, "database": db_ok, "redis": redis_ok}


# Serve the built frontend (single-process deployments); nginx handles this
# in the Docker stack instead.
_dist = ROOT_DIR / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
