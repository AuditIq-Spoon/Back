"""
POST   /sessions         — Create a new audit session and trigger the pipeline.
GET    /sessions         — List all sessions (dashboard).
GET    /sessions/{id}    — Get a single session with full anomaly detail.
"""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime
from uuid import uuid4, UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from ..core import data_service
from ..core.config import get_settings
from ..models.schemas import (
    AuditSession,
    AuditSessionCreate,
    AuditSessionListItem,
    AuditType,
    SessionStatus,
)
from ..services.websocket_manager import manager as ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sessions", tags=["sessions"])


# ---------------------------------------------------------------------------
# POST /sessions
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=AuditSession,
    status_code=status.HTTP_201_CREATED,
    summary="Create an audit session and trigger the AI pipeline",
)
async def create_session(
    body: AuditSessionCreate,
    background_tasks: BackgroundTasks,
) -> AuditSession:
    session_id = uuid4()
    params_dict = body.params.model_dump()
    now = datetime.utcnow()

    db_record = {
        "id": str(session_id),
        "audit_type": body.params.audit_type.value,
        "status": SessionStatus.PENDING.value,
        "params": params_dict,
        "risk_score": None,
        "risk_summary": None,
        "anomalies": [],
        "created_at": now.isoformat(),
        "completed_at": None,
    }

    try:
        await data_service.create_session(db_record)
    except Exception as exc:
        logger.error("Failed to create session: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Database write failed. Please try again.",
        ) from exc

    background_tasks.add_task(
        _run_audit_pipeline, str(session_id), body.params.audit_type, params_dict
    )

    return AuditSession(
        id=session_id,
        audit_type=body.params.audit_type,
        status=SessionStatus.PENDING,
        params=params_dict,
        risk_score=None,
        anomalies=[],
        created_at=now,
    )


# ---------------------------------------------------------------------------
# GET /sessions
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=list[AuditSessionListItem],
    summary="List all audit sessions for the dashboard",
)
async def list_sessions() -> list[AuditSessionListItem]:
    try:
        rows = await data_service.list_sessions()
        return [AuditSessionListItem(**row) for row in rows]
    except Exception as exc:
        logger.error("Failed to fetch sessions: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not retrieve sessions.",
        ) from exc


# ---------------------------------------------------------------------------
# GET /sessions/{session_id}
# ---------------------------------------------------------------------------

@router.get(
    "/{session_id}",
    response_model=AuditSession,
    summary="Get full detail of a single audit session",
)
async def get_session(session_id: UUID) -> AuditSession:
    try:
        row = await data_service.get_session(str(session_id))
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found.",
            )
        return AuditSession(**row)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to fetch session %s: %s", session_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not retrieve session.",
        ) from exc


# ---------------------------------------------------------------------------
# Background pipeline task
# ---------------------------------------------------------------------------

PROGRESS_STEPS_INOUT = [
    "Initializing audit session",
    "Fetching bank statements & invoices",
    "Fetching quotes & price books",
    "Packaging data for AI engine",
    "Triggering AI pipeline",
    "Waiting for AI result",
]

PROGRESS_STEPS_TENDER = [
    "Initializing audit session",
    "Fetching bids & market documents",
    "Cross-referencing tender winner",
    "Packaging data for AI engine",
    "Triggering AI pipeline",
    "Waiting for AI result",
]


async def _run_audit_pipeline(
    session_id: str,
    audit_type: AuditType,
    params: dict,
) -> None:
    steps = PROGRESS_STEPS_INOUT if audit_type == AuditType.INOUT else PROGRESS_STEPS_TENDER
    total = len(steps)

    async def progress(step_idx: int, detail: str | None = None, done: bool = False) -> None:
        await ws_manager.send_progress(
            session_id=session_id,
            step=step_idx + 1,
            total_steps=total,
            label=steps[step_idx],
            detail=detail,
            status="DONE" if done else "RUNNING",
        )
        await asyncio.sleep(0.6)

    try:
        await data_service.update_session(session_id, {"status": SessionStatus.RUNNING.value})
        await progress(0, done=True)

        documents = await _fetch_documents(audit_type, params, progress)

        await progress(total - 3, f"Collected {len(documents)} document(s).", done=True)
        await progress(total - 2, "Firing pipeline.", done=True)

        settings = get_settings()
        if settings.use_mock_n8n:
            # Simulate processing delay then return a mock result
            await progress(total - 1, "AI is processing…")
            await asyncio.sleep(2)
            await _deliver_mock_result(session_id, audit_type, documents)
        else:
            from ..services import n8n_service
            success = await n8n_service.trigger_audit(
                session_id=UUID(session_id),
                audit_type=audit_type,
                session_params=params,
                documents=documents,
            )
            if not success:
                await data_service.update_session(session_id, {"status": SessionStatus.FAILED.value})
                await ws_manager.send_error(session_id, "n8n webhook failed. Please retry.")
                return
            await progress(total - 1, "AI pipeline is processing. Results will appear shortly.")

    except Exception as exc:
        logger.exception("Audit pipeline crashed for session %s: %s", session_id, exc)
        await data_service.update_session(session_id, {"status": SessionStatus.FAILED.value})
        await ws_manager.send_error(session_id, str(exc))


async def _fetch_documents(
    audit_type: AuditType,
    params: dict,
    progress_fn,
) -> list[dict]:
    if audit_type == AuditType.INOUT:
        await progress_fn(1, "Querying bank statements and invoices.", done=True)
        bank_inv = await data_service.list_documents(
            types=["BANK_STATEMENT", "INVOICE"],
            start_date=params.get("start_date"),
            end_date=params.get("end_date"),
        )
        await progress_fn(2, "Querying quotes and price books.", done=True)
        quotes = await data_service.list_documents(types=["QUOTE", "PRICE_BOOK"])
        return bank_inv + quotes
    else:
        tender_id = params.get("tender_id")
        await progress_fn(1, f"Querying bids for project: {params.get('project_name')}.", done=True)
        docs = await data_service.list_documents(
            types=["BID", "MARKET_PLACE", "QUOTE"],
            tender_id=tender_id or None,
        )
        # Cross-reference: lookup tender winner
        if tender_id:
            tender = await data_service.get_tender(tender_id)
            await progress_fn(
                2,
                f"Winner: {tender['winner']['company']}" if tender and tender.get("winner") else "No winner assigned yet.",
                done=True,
            )
        else:
            await progress_fn(2, "No specific tender selected.", done=True)
        return docs


async def _deliver_mock_result(
    session_id: str,
    audit_type: AuditType,
    documents: list[dict],
) -> None:
    """Generate and deliver a simulated audit result when n8n is not configured."""
    score = random.randint(15, 85)

    if audit_type == AuditType.INOUT:
        anomalies = [
            {
                "code": "OVERBILLING",
                "severity": "HIGH",
                "description": "Invoice amount is 20% above the approved quote.",
                "affected_documents": ["INV-2024-0105.pdf"],
                "delta_amount": 2000.0,
            },
            {
                "code": "DUPLICATE_PAYMENT",
                "severity": "CRITICAL",
                "description": "Same invoice reference was paid twice within 24 hours.",
                "affected_documents": ["bank_statement_oct.pdf"],
                "delta_amount": 14400.0,
            },
        ]
        summary = (
            f"Mock audit identified {len(anomalies)} anomaly(ies). "
            "Detected potential overbilling and a duplicate payment referencing the same invoice. "
            "Manual verification is recommended before processing further payments."
        )
    else:
        anomalies = [
            {
                "code": "PREFERRED_VENDOR",
                "severity": "MEDIUM",
                "description": "Winning bid is 15% above the median market price.",
                "affected_documents": [],
                "delta_amount": None,
            },
        ]
        summary = (
            "Mock tender audit completed. "
            "The selected vendor's bid is slightly above the market median. "
            "No critical irregularities detected but a price-justification memo is advisable."
        )

    now = datetime.utcnow().isoformat()
    await data_service.update_session(
        session_id,
        {
            "status": SessionStatus.COMPLETED.value,
            "risk_score": score,
            "risk_summary": summary,
            "anomalies": anomalies,
            "completed_at": now,
        },
    )

    await ws_manager.send_result(
        session_id=session_id,
        risk_score=score,
        risk_summary=summary,
        anomalies=anomalies,
    )
