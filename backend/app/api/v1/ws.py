from __future__ import annotations

import jwt as pyjwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.security import decode_token
from app.ws.manager import manager

router = APIRouter(tags=["ws"])


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = Query(...)) -> None:
    try:
        payload = decode_token(token, "access")
    except pyjwt.InvalidTokenError:
        await ws.close(code=4401)
        return
    user_id = int(payload["sub"])
    role = payload.get("role", "staff")
    await manager.connect(ws, user_id, role)
    try:
        while True:
            # client messages are just keep-alives; we only push
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws)
