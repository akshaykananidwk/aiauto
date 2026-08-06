"""Simple Redis fixed-window rate limiting middleware."""
from __future__ import annotations

import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.services.redis_client import get_redis


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or not request.url.path.startswith("/api"):
            return await call_next(request)
        settings = get_settings()
        is_login = request.url.path.endswith("/auth/login")
        limit = settings.login_rate_limit_per_minute if is_login else settings.rate_limit_per_minute
        client_ip = request.client.host if request.client else "unknown"
        window = int(time.time() // 60)
        key = f"aiauto:ratelimit:{'login' if is_login else 'api'}:{client_ip}:{window}"
        try:
            redis = get_redis()
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, 70)
            if count > limit:
                return JSONResponse(
                    {"detail": "Too many requests, slow down."}, status_code=429
                )
        except Exception:
            pass  # Redis unavailable — do not block traffic
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response
