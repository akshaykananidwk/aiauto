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
    version="1.3.0",
    description="Central AI automation platform: staff submit prompts, a queue "
    "dispatches them to the master computer's managed ChatGPT Pro browser "
    "session, and results (text, images, files) come back — without staff "
    "ever touching the account. The public REST API (X-API-Key) lets your "
    "own websites, ERPs, CRMs and apps integrate with the platform.",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
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

from app.api.public_v1 import router as public_router  # noqa: E402

app.include_router(public_router)


@app.middleware("http")
async def record_public_api_usage(request, call_next):
    """Success/error counters per API key for the developer dashboard."""
    response = await call_next(request)
    key_id = getattr(request.state, "api_key_id", None)
    if key_id is not None:
        from app.services.api_usage import record_request

        try:
            await record_request(key_id, response.status_code < 400)
        except Exception:
            pass
        remaining = getattr(request.state, "api_rate_remaining", None)
        if remaining is not None:
            response.headers["X-RateLimit-Remaining"] = str(remaining)
    return response


@app.get("/api/openapi.yaml", include_in_schema=False)
async def openapi_yaml():
    """The OpenAPI spec as downloadable YAML (JSON is at /api/openapi.json)."""
    import yaml
    from fastapi.responses import Response

    return Response(
        yaml.safe_dump(app.openapi(), sort_keys=False, allow_unicode=True),
        media_type="application/yaml",
        headers={"Content-Disposition": "attachment; filename=aiauto-openapi.yaml"},
    )


@app.get("/api/health")
async def health() -> dict:
    """Liveness + dependency health, used by the start script and monitors.
    Hard-capped so a down dependency can never stall this endpoint."""
    import asyncio

    db_ok = redis_ok = False
    try:
        from app.db.session import async_session_factory

        async with async_session_factory() as db:
            await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=3)
        db_ok = True
    except Exception:
        pass
    try:
        redis_ok = bool(await asyncio.wait_for(get_redis().ping(), timeout=2))
    except Exception:
        pass
    worker_online = chrome_connected = False
    try:
        from app.services.queue import QueueService

        ws = await asyncio.wait_for(QueueService().worker_status(), timeout=2)
        worker_online = ws["worker_online"]
        chrome_connected = ws["chrome_connected"]
    except Exception:
        pass
    status = "ok" if (db_ok and redis_ok) else "degraded"
    return {
        "status": status,
        "app": settings.app_name,
        "database": db_ok,
        "redis": redis_ok,
        "worker": worker_online,
        "chrome": chrome_connected,
    }


# Serve the built frontend (single-process deployments); nginx handles this
# in the Docker stack instead.
_dist = ROOT_DIR / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
