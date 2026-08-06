"""Outbound webhooks: signed deliveries with automatic retries.

Deliveries POST JSON with these headers:

    X-AIAuto-Event:     job.completed
    X-AIAuto-Timestamp: 1786050000
    X-AIAuto-Signature: hex(HMAC_SHA256(secret, f"{timestamp}.{body}"))

Consumers verify the signature and reject stale timestamps (replay
protection). Failures are retried with backoff (3 attempts total).
Dispatch works from both the API server and the worker process.
"""
from __future__ import annotations

import asyncio
import json
import time

import httpx
from sqlalchemy import select

from app.core.logging import get_logger
from app.core.security import decrypt_secret, sign_webhook
from app.db.session import async_session_factory
from app.models.webhook import Webhook

logger = get_logger("webhooks")

RETRY_DELAYS = [0, 10, 60]  # seconds before each of the 3 attempts
DELIVERY_TIMEOUT = 15


async def _deliver(webhook_id: int, url: str, secret: str, event: str, payload: dict) -> None:
    body = json.dumps({"event": event, "data": payload}, default=str).encode("utf-8")
    status: int | None = None
    for attempt, delay in enumerate(RETRY_DELAYS, start=1):
        if delay:
            await asyncio.sleep(delay)
        timestamp = str(int(time.time()))
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "AIAuto-Webhook/1.0",
            "X-AIAuto-Event": event,
            "X-AIAuto-Timestamp": timestamp,
            "X-AIAuto-Signature": sign_webhook(secret, timestamp, body),
        }
        try:
            async with httpx.AsyncClient(timeout=DELIVERY_TIMEOUT) as client:
                resp = await client.post(url, content=body, headers=headers)
            status = resp.status_code
            if 200 <= status < 300:
                break
            logger.warning("webhook %s attempt %s got HTTP %s", webhook_id, attempt, status)
        except Exception as exc:
            status = None
            logger.warning("webhook %s attempt %s failed: %s", webhook_id, attempt, exc)

    # record the outcome with a fresh session (we may be minutes later)
    try:
        from datetime import datetime, timezone

        async with async_session_factory() as db:
            hook = await db.get(Webhook, webhook_id)
            if hook is not None:
                hook.last_status = status
                hook.last_delivery_at = datetime.now(timezone.utc)
                if status is not None and 200 <= status < 300:
                    hook.failure_count = 0
                else:
                    hook.failure_count += 1
                await db.commit()
    except Exception as exc:
        logger.warning("could not record webhook outcome: %s", exc)


async def dispatch(user_id: int, event: str, payload: dict) -> int:
    """Fire-and-forget delivery to every matching active webhook of the
    user. Returns how many deliveries were scheduled. Never raises."""
    try:
        async with async_session_factory() as db:
            res = await db.execute(
                select(Webhook).where(Webhook.user_id == user_id,
                                      Webhook.is_active.is_(True))
            )
            hooks = [
                (h.id, h.url, decrypt_secret(h.secret_encrypted))
                for h in res.scalars().all()
                if not h.events or event in h.events
            ]
    except Exception as exc:
        logger.warning("webhook lookup failed: %s", exc)
        return 0

    for hook_id, url, secret in hooks:
        if not secret:
            continue
        try:
            asyncio.get_running_loop().create_task(
                _deliver(hook_id, url, secret, event, payload))
        except RuntimeError:
            pass  # no running loop (sync context) — skip silently
    return len(hooks)
