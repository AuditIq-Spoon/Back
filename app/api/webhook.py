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
    When a file upload triggers the INOUT workflow (yhs1QhteOspEbuDN) with a synthetic
    session_id, n8n POSTs here. We persist nothing to audit_sessions; we store a compact
    result keyed by document_id so GET /api/upload/n8n-status/{id} can serve the SPA.
    """
    from ..services.upload_n8n_result_store import record_result

    doc_id = _extract_upload_document_id(payload)
    anomalies_raw = payload.get("anomalies") or []
    if not isinstance(anomalies_raw, list):
        anomalies_raw = []
    anomalies: list[dict[str, Any]] = []
    for a in anomalies_raw:
        if isinstance(a, dict):
            anomalies.append(a)
        elif hasattr(a, "model_dump"):
            anomalies.append(a.model_dump())

    try:
        risk_score = int(payload.get("risk_score", 0))
    except (TypeError, ValueError):
        risk_score = 0
    risk_summary = str(payload.get("risk_summary") or "").strip() or "No summary returned."

    if doc_id:
        record_result(
            doc_id,
            {
                "status": "ready",
                "document_id": doc_id,
                "session_id": str(payload.get("session_id") or ""),
                "risk_score": max(0, min(100, risk_score)),
                "risk_summary": risk_summary,
                "anomalies": anomalies,
                "processing_metadata": payload.get("processing_metadata")
                if isinstance(payload.get("processing_metadata"), dict)
                else {},
            },
        )
    else:
        logger.warning(
            "n8n upload callback missing document_id — add document_id to HTTP Request JSON "
            "(payload includes document_id from webhook trigger). session_id=%s keys=%s",
            payload.get("session_id"),
            list(payload.keys()),
        )

    logger.info(
        "n8n upload-triggered audit finished — document_id=%s session_id=%s risk_score=%s flags=%d",
        doc_id,
        payload.get("session_id"),
        risk_score,
        len(anomalies),
    )
    return {"status": "ok", "session_id": str(payload.get("session_id", "")), "document_id": doc_id or ""}


def _extract_upload_document_id(payload: dict[str, Any]) -> str | None:
    for key in ("document_id", "documentId"):
        v = payload.get(key)
        if v not in (None, "", []):
            return str(v)
    docs = payload.get("documents")
    if isinstance(docs, list) and docs:
        d0 = docs[0]
        if isinstance(d0, dict) and d0.get("id"):
            return str(d0["id"])
    return None
