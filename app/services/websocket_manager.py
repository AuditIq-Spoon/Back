"""
WebSocket Connection Manager.

Maintains a registry of active WebSocket connections keyed by session_id.
Provides broadcast helpers so any service layer can push progress events
to the connected frontend without a circular import.

Thread safety: FastAPI runs on a single-threaded async event loop, so the
plain dict is safe here. If you scale to multiple workers, replace this
with a Redis pub/sub backend (e.g. via aioredis).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages active WebSocket connections per audit session."""

    def __init__(self) -> None:
        # Maps session_id (str) → list of active WebSocket connections.
        # Multiple browser tabs may connect to the same session.
        self._connections: dict[str, list[WebSocket]] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        """Accept the handshake and register the connection."""
        await websocket.accept()
        self._connections.setdefault(session_id, []).append(websocket)
        logger.info(
            "WebSocket connected: session=%s, total=%d",
            session_id,
            len(self._connections[session_id]),
        )

    async def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        """Remove a closed connection from the registry."""
        connections = self._connections.get(session_id, [])
        if websocket in connections:
            connections.remove(websocket)
        if not connections:
            self._connections.pop(session_id, None)
        logger.info("WebSocket disconnected: session=%s", session_id)

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    async def send_progress(
        self,
        session_id: str,
        step: int,
        total_steps: int,
        label: str,
        detail: str | None = None,
        status: str = "RUNNING",
        extra: dict[str, Any] | None = None,
    ) -> None:
        """
        Broadcast a structured progress event to all listeners of a session.

        Payload schema (mirrors ProgressStep Pydantic model):
        {
          "type": "PROGRESS",
          "session_id": "...",
          "step": 3,
          "total_steps": 6,
          "label": "Running deterministic checks...",
          "detail": "Comparing invoice totals against bank debits",
          "status": "RUNNING",   // PENDING | RUNNING | DONE | ERROR
          "timestamp": "2024-01-01T12:00:00Z"
        }
        """
        payload: dict[str, Any] = {
            "type": "PROGRESS",
            "session_id": session_id,
            "step": step,
            "total_steps": total_steps,
            "label": label,
            "detail": detail,
            "status": status,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        if extra:
            payload.update(extra)
        await self._broadcast(session_id, payload)

    async def send_result(
        self,
        session_id: str,
        risk_score: int,
        risk_summary: str,
        anomalies: list[dict[str, Any]],
    ) -> None:
        """
        Broadcast the final audit result once n8n has responded.

        Payload schema:
        {
          "type": "RESULT",
          "session_id": "...",
          "risk_score": 95,
          "risk_summary": "Critical overbilling detected...",
          "anomalies": [...],
          "timestamp": "..."
        }
        """
        payload: dict[str, Any] = {
            "type": "RESULT",
            "session_id": session_id,
            "risk_score": risk_score,
            "risk_summary": risk_summary,
            "anomalies": anomalies,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        await self._broadcast(session_id, payload)

    async def send_error(self, session_id: str, message: str) -> None:
        """Broadcast an error event so the frontend can show a failure state."""
        payload: dict[str, Any] = {
            "type": "ERROR",
            "session_id": session_id,
            "message": message,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        await self._broadcast(session_id, payload)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _broadcast(self, session_id: str, payload: dict[str, Any]) -> None:
        """
        Send a JSON message to every WebSocket connected to the given session.
        Silently removes broken connections.
        """
        connections = self._connections.get(session_id, [])
        dead: list[WebSocket] = []

        for ws in connections:
            try:
                await ws.send_text(json.dumps(payload))
            except Exception:
                dead.append(ws)

        for ws in dead:
            await self.disconnect(session_id, ws)

    def is_anyone_listening(self, session_id: str) -> bool:
        """Returns True if at least one client is connected for this session."""
        return bool(self._connections.get(session_id))


# Singleton — import this instance everywhere
manager = WebSocketManager()
