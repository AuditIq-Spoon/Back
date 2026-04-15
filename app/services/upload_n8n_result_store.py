"""
In-memory store for n8n upload-workflow callbacks (workflow document uploads).

Used so the frontend can poll GET /api/upload/n8n-status/{document_id} after upload.
Not durable across restarts or multiple workers — replace with Redis/DB if needed.
"""
from __future__ import annotations

import threading
import time
from typing import Any

_lock = threading.Lock()
_store: dict[str, tuple[float, dict[str, Any]]] = {}
TTL_SEC = 3600


def record_result(document_id: str, payload: dict[str, Any]) -> None:
    if not document_id:
        return
    with _lock:
        _store[str(document_id)] = (time.time() + TTL_SEC, dict(payload))


def get_result(document_id: str) -> dict[str, Any] | None:
    now = time.time()
    with _lock:
        dead = [k for k, (exp, _) in _store.items() if exp < now]
        for k in dead:
            del _store[k]
        row = _store.get(str(document_id))
        if not row:
            return None
        exp, data = row
        if exp < now:
            del _store[str(document_id)]
            return None
        return data


def mark_pending(document_id: str) -> None:
    """Reserve a slot so the UI can poll before n8n returns. Does not overwrite a ready result."""
    if not document_id:
        return
    key = str(document_id)
    with _lock:
        row = _store.get(key)
        if row:
            _, data = row
            if data.get("status") == "ready" or "risk_score" in data:
                return
        _store[key] = (time.time() + TTL_SEC, {"status": "pending", "document_id": key})
