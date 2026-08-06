from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import jwt as pyjwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.security import decode_token
from app.db.session import async_session_factory
from app.models.user import User
from app.services.auth_guard import is_revoked
from app.ws.manager import manager

router = APIRouter(tags=["ws"])

REAUTH_INTERVAL_SECONDS = 300  # periodic re-check of the user's is_active


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = Query(...)) -> None:
    try:
        payload = decode_token(token, "access")
    except pyjwt.InvalidTokenError:
        await ws.close(code=4401)
        return
    if await is_revoked(payload.get("jti", "")):
        await ws.close(code=4401)
        return
    user_id = int(payload["sub"])

    # authorization is verified against the DB, not just the token claims
    async with async_session_factory() as db:
        user = await db.get(User, user_id)
        if user is None or not user.is_active:
            await ws.close(code=4403)
            return
        role = user.role.value

    exp = float(payload.get("exp", 0))
    await manager.connect(ws, user_id, role)
    last_reauth = asyncio.get_event_loop().time()
    try:
        while True:
            # close when the access token expires — the client reconnects
            # with a fresh token, so deactivated users lose the stream
            remaining = exp - datetime.now(timezone.utc).timestamp()
            if remaining <= 0:
                await ws.close(code=4401)
                return
            try:
                await asyncio.wait_for(
                    ws.receive_text(), timeout=min(remaining, REAUTH_INTERVAL_SECONDS)
                )
            except asyncio.TimeoutError:
                pass  # no keepalive within the window — fall through to re-check
            now = asyncio.get_event_loop().time()
            if now - last_reauth >= REAUTH_INTERVAL_SECONDS:
                last_reauth = now
                async with async_session_factory() as db:
                    user = await db.get(User, user_id)
                    if user is None or not user.is_active:
                        await ws.close(code=4403)
                        return
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws)
