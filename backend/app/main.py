"""AIAuto — Central AI Automation Platform (API server)."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.core.rate_limit import RateLimitMiddleware, SecurityHeadersMiddleware
from app.db.session import init_db
from app.services.redis_client import close_redis
from app.ws.manager import manager

logger = get_logger("main")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings.ensure_dirs()
    await init_db()
    manager.start()
    logger.info("%s started (env=%s)", settings.app_name, settings.env)
    yield
    await manager.stop()
    await close_redis()
    logger.info("shutdown complete")


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Central AI automation platform: staff submit prompts, a queue "
    "dispatches them to the master computer's ChatGPT session, and results "
    "(text, images, files) come back — without staff ever touching the account.",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
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
    return {"status": "ok", "app": settings.app_name}
