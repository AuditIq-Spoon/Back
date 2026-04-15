"""
n8n Service — packages extracted document data into a structured JSON payload
and fires it at the appropriate n8n Webhook URL to trigger the AI audit pipeline.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx

from ..core.config import get_settings
from ..models.schemas import AuditType

logger = logging.getLogger(__name__)


def _json_safe(value: Any) -> Any:
    """Round-trip through JSON so httpx can serialize floats, dates, etc."""
    return json.loads(json.dumps(value, default=str))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def trigger_audit(
    session_id: UUID,
    audit_type: AuditType,
    session_params: dict[str, Any],
    documents: list[dict[str, Any]],
) -> bool:
    """
    Builds the n8n payload and POSTs it to the correct webhook URL.

    Returns True on success (2xx from n8n), False otherwise.
    The caller is responsible for updating the session status.
    """
    settings = get_settings()
    webhook_url = (
        settings.N8N_WEBHOOK_INOUT_URL
        if audit_type == AuditType.INOUT
        else settings.N8N_WEBHOOK_TENDER_URL
    )

    payload = _build_payload(session_id, audit_type, session_params, documents)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            logger.info(
                "n8n webhook triggered for session %s — HTTP %s",
                session_id,
                response.status_code,
            )
            return True
    except httpx.HTTPStatusError as exc:
        logger.error(
            "n8n webhook returned error %s for session %s: %s",
            exc.response.status_code,
            session_id,
            exc.response.text,
        )
    except httpx.RequestError as exc:
        logger.error(
            "Failed to reach n8n webhook for session %s: %s",
            session_id,
            str(exc),
        )
    return False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_payload(
    session_id: UUID,
    audit_type: AuditType,
    session_params: dict[str, Any],
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Constructs the canonical JSON payload consumed by the n8n Webhook Trigger node.

    Schema:
    {
      "session_id":    "<uuid>",
      "audit_type":    "INOUT" | "TENDER",
      "callback_url":  "<FastAPI base>/api/webhook/n8n-result",
      "params":        { ...session-specific params... },
      "documents": [
        {
          "id":             "<uuid>",
          "filename":       "invoice.pdf",
          "document_type":  "INVOICE",
          "extracted_json": { ...OCR output... }
        },
        ...
      ]
    }
    """
    settings = get_settings()
    # Derive the callback URL from our own base URL, configured in env
    base_url = getattr(settings, "API_BASE_URL", "http://localhost:8000")

    return {
        "session_id": str(session_id),
        "audit_type": audit_type.value,
        "callback_url": f"{base_url}/api/webhook/n8n-result",
        "params": session_params,
        "documents": [
            {
                "id": str(doc.get("id", "")),
                "filename": doc.get("filename", ""),
                "document_type": doc.get("document_type", "OTHER"),
                "extracted_json": doc.get("extracted_json", {}),
            }
            for doc in documents
        ],
    }


# ---------------------------------------------------------------------------
# Document upload → n8n (per-file workflow)
# ---------------------------------------------------------------------------

async def trigger_document_upload(document_row: dict[str, Any]) -> None:
    """
    POSTs to N8N_WEBHOOK_DOCUMENT_UPLOAD_URL using the **same JSON shape** as
    POST /sessions → INOUT audit (`session_id`, `audit_type`, `callback_url`,
    `params`, `documents[]`) so the AuditIQ INOUT webhook workflow can run.

    `callback_url` points to `/api/webhook/n8n-result-upload` so n8n does not
    try to persist results against a non-existent `audit_sessions` row.
    """
    settings = get_settings()
    url = (settings.N8N_WEBHOOK_DOCUMENT_UPLOAD_URL or "").strip()
    if not url:
        logger.warning(
            "Document n8n webhook NOT called: N8N_WEBHOOK_DOCUMENT_UPLOAD_URL is empty. "
            "Set it in backend/.env to the Webhook node's Production URL (workflow ref %s). "
            "document_id=%s",
            settings.N8N_UPLOAD_WORKFLOW_ID,
            document_row.get("id"),
        )
        return

    base_url = getattr(settings, "API_BASE_URL", "http://localhost:8000").rstrip("/")
    txn = (document_row.get("transaction_date") or "").strip() or date.today().isoformat()
    # Use next calendar day for end_date so it satisfies INOUT "end after start" if workflow validates
    try:
        end_s = (date.fromisoformat(txn) + timedelta(days=1)).isoformat()
    except ValueError:
        end_s = txn

    session_id = uuid4()
    params: dict[str, Any] = {
        "audit_type": "INOUT",
        "start_date": txn,
        "end_date": end_s,
    }
    doc_payload = {
        "id": str(document_row.get("id", "")),
        "filename": document_row.get("filename") or "",
        "document_type": document_row.get("document_type") or "OTHER",
        "extracted_json": document_row.get("extracted_json") or {},
    }

    try:
        payload: dict[str, Any] = _json_safe(
            _build_payload(session_id, AuditType.INOUT, params, [doc_payload])
        )
        payload["callback_url"] = f"{base_url}/api/webhook/n8n-result-upload"
        # Echo back in n8n HTTP Request node body so the upload UI can poll by document_id
        payload["document_id"] = str(document_row.get("id", ""))
        fe = (settings.FRONTEND_PUBLIC_URL or "").strip().rstrip("/")
        if fe:
            payload["frontend_upload_page_url"] = f"{fe}/upload"
    except (TypeError, ValueError) as exc:
        logger.exception(
            "Document n8n payload could not be built for %s: %s",
            document_row.get("id"),
            exc,
        )
        return

    headers = {"Content-Type": "application/json"}
    if settings.N8N_SECRET:
        headers["X-N8n-Secret"] = settings.N8N_SECRET

    try:
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
        logger.info(
            "Document → n8n INOUT webhook OK — workflow_ref=%s document_id=%s session_id=%s HTTP %s",
            settings.N8N_UPLOAD_WORKFLOW_ID,
            document_row.get("id"),
            session_id,
            resp.status_code,
        )
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Document n8n webhook HTTP %s for %s: %s",
            exc.response.status_code,
            document_row.get("id"),
            exc.response.text[:2000],
        )
    except httpx.RequestError as exc:
        logger.error(
            "Document n8n webhook unreachable for %s: %s",
            document_row.get("id"),
            str(exc),
        )
    except Exception as exc:
        logger.exception(
            "Document n8n webhook unexpected error for %s: %s",
            document_row.get("id"),
            exc,
        )
