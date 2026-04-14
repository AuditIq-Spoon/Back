"""
WS /ws/progress/{session_id}

Real-time progress streaming endpoint.
The frontend connects here after creating a session and receives
structured JSON events until the audit completes or fails.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..services.websocket_manager import manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


@router.websocket("/ws/progress/{session_id}")
async def websocket_progress(websocket: WebSocket, session_id: str) -> None:
    """
    Lifecycle:
    1. Client connects → registered in the WebSocketManager.
    2. Manager broadcasts progress events triggered by the audit pipeline.
    3. Client disconnects (or audit ends) → cleaned up automatically.

    The client may send a "PING" text frame to keep the connection alive;
    the server will echo back "PONG".
    """
    await manager.connect(session_id, websocket)
    logger.info("WS client connected for session %s", session_id)

    try:
        while True:
            # Keep reading to detect disconnects and handle keep-alives
            data = await websocket.receive_text()
            if data.strip().upper() == "PING":
                await websocket.send_text("PONG")
    except WebSocketDisconnect:
        logger.info("WS client disconnected from session %s", session_id)
    finally:
        await manager.disconnect(session_id, websocket)
