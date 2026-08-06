"""WebSocket connection manager + Redis pub/sub bridge.

Staff connections receive only events targeted at their own user_id.
Admin connections additionally receive admin_only events and every
user-targeted event (admins see everything).
"""
from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import WebSocket

from app.core.logging import get_logger
from app.services.events import CHANNEL
from app.services.redis_client import get_redis

logger = get_logger("ws")


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: dict[WebSocket, tuple[int, str]] = {}  # ws -> (user_id, role)
        self._listener_task: asyncio.Task | None = None

    async def connect(self, ws: WebSocket, user_id: int, role: str) -> None:
        await ws.accept()
        self.connections[ws] = (user_id, role)

    def disconnect(self, ws: WebSocket) -> None:
        self.connections.pop(ws, None)

    async def _deliver(self, payload: dict) -> None:
        target_user = payload.get("user_id")
        admin_only = payload.get("admin_only", False)
        dead: list[WebSocket] = []
        for ws, (user_id, role) in list(self.connections.items()):
            is_admin = role == "admin"
            allowed = is_admin or (not admin_only and target_user == user_id)
            if not allowed:
                continue
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def _listen(self) -> None:
        while True:
            try:
                redis = get_redis()
                pubsub = redis.pubsub()
                await pubsub.subscribe(CHANNEL)
                async for message in pubsub.listen():
                    if message["type"] != "message":
                        continue
                    with contextlib.suppress(Exception):
                        await self._deliver(json.loads(message["data"]))
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning("event listener reconnecting after error: %s", exc)
                await asyncio.sleep(2)

    def start(self) -> None:
        if self._listener_task is None or self._listener_task.done():
            self._listener_task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listener_task


manager = ConnectionManager()
