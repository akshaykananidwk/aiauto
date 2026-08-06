"""Realtime event bus.

Events are published to a Redis pub/sub channel so that the worker process
(possibly on another machine) and the API server share one bus. The API
server bridges the channel to connected WebSocket clients.

Event payload convention:
    {
      "type": "prompt.completed" | "prompt.processing" | ... ,
      "user_id": 42,          # target staff user (also delivered to admins)
      "admin_only": false,    # deliver only to admins
      "data": {...}
    }
"""
from __future__ import annotations

import json
from typing import Any

from app.services.redis_client import get_redis

CHANNEL = "aiauto:events"

# well-known event types
PROMPT_SUBMITTED = "prompt.submitted"
PROMPT_PROCESSING = "prompt.processing"
PROMPT_GENERATING = "prompt.generating"
PROMPT_GENERATING_IMAGE = "prompt.generating_image"
PROMPT_DOWNLOADING = "prompt.downloading"
PROMPT_COMPLETED = "prompt.completed"
PROMPT_FAILED = "prompt.failed"
PROMPT_CANCELLED = "prompt.cancelled"
QUEUE_UPDATED = "queue.updated"
UPDATE_PROGRESS = "update.progress"
WORKER_STATUS = "worker.status"


async def publish(
    event_type: str,
    data: dict[str, Any] | None = None,
    *,
    user_id: int | None = None,
    admin_only: bool = False,
) -> None:
    payload = {
        "type": event_type,
        "user_id": user_id,
        "admin_only": admin_only,
        "data": data or {},
    }
    await get_redis().publish(CHANNEL, json.dumps(payload, default=str))
    # plugin hooks run in the publishing process, best-effort
    try:
        from app.services.plugins import hooks

        await hooks.dispatch(event_type, payload)
    except Exception:
        pass
