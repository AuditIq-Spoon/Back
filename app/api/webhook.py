"""
POST /webhook/n8n-result

Endpoint called by n8n once the AI pipeline has finished processing.
Stores the final risk score and anomalies in Supabase, then broadcasts
the RESULT event over the session's WebSocket.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ..core import data_service
from ..core.security import verify_n8n_secret
from ..models.schemas import RiskResult, SessionStatus
from ..services.websocket_manager import manager as ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.post(
    "/n8n-result",
    status_code=status.HTTP_200_OK,
    summary="Receive final audit result from the n8n AI engine",
    dependencies=[Depends(verify_n8n_secret)],
)
async def receive_n8n_result(payload: RiskResult) -> dict:
    """
    1. Validates the shared secret header (dependency).
    2. Persists the risk score and anomaly list to Supabase.
    3. Marks the session as COMPLETED.
    4. Broadcasts the final RESULT event to all connected WebSocket clients.
    """
    session_id = str(payload.session_id)
    now = datetime.utcnow().isoformat()

    update_data = {
        "status": SessionStatus.COMPLETED.value,
        "risk_score": payload.risk_score,
        "risk_summary": payload.risk_summary,
        "anomalies": [a.model_dump() for a in payload.anomalies],
        "completed_at": now,
    }

    try:
        await data_service.update_session(session_id, update_data)
    except Exception as exc:
        logger.error("Failed to persist n8n result for session %s: %s", session_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Database write failed.",
        ) from exc

    # Push the final result to the live audit view
    await ws_manager.send_result(
        session_id=session_id,
        risk_score=payload.risk_score,
        risk_summary=payload.risk_summary,
        anomalies=[a.model_dump() for a in payload.anomalies],
    )

    # Send a final DONE progress step
    await ws_manager.send_progress(
        session_id=session_id,
        step=6,
        total_steps=6,
        label="Audit complete",
        detail=f"Risk Score: {payload.risk_score}/100",
        status="DONE",
    )

    logger.info(
        "Audit result stored for session %s — Risk Score: %d",
        session_id,
        payload.risk_score,
    )
    return {"status": "ok", "session_id": session_id}


@router.post(
    "/n8n-result-upload",
    status_code=status.HTTP_200_OK,
    summary="Receive n8n result for upload-triggered runs (does not update audit_sessions)",
    dependencies=[Depends(verify_n8n_secret)],
)
async def receive_n8n_upload_result(payload: dict[str, Any]) -> dict:
    """
    When a file upload triggers the INOUT workflow with a synthetic session_id,
    the workflow still POSTs a risk payload. This endpoint accepts it so n8n
    succeeds without writing to `audit_sessions` (those IDs are not real sessions).
    """
    logger.info(
        "n8n upload-triggered audit finished — session_id=%s risk_score=%s flags=%d",
        payload.get("session_id"),
        payload.get("risk_score"),
        len(payload.get("anomalies") or []),
    )
    return {"status": "ok", "session_id": str(payload.get("session_id", ""))}
