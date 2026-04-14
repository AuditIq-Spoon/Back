"""
GET /documents — List uploaded documents.

Query params:
  • No dates        → every document, newest first.
  • start_date + end_date → only documents whose transaction_date falls in
    the inclusive range (same logic as INOUT audit session document fetch).
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from ..core import data_service
from ..models.schemas import DocumentListItem, DocumentType

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


def _row_to_item(row: dict) -> DocumentListItem:
    dt = row.get("document_type", "OTHER")
    try:
        doc_type = DocumentType(dt) if isinstance(dt, str) else dt
    except ValueError:
        doc_type = DocumentType.OTHER

    uploaded = row.get("uploaded_at")
    if isinstance(uploaded, datetime):
        uploaded_parsed = uploaded
    elif isinstance(uploaded, str):
        s = uploaded.replace("Z", "").split("+")[0].strip()
        uploaded_parsed = datetime.fromisoformat(s)
    else:
        uploaded_parsed = datetime.utcnow()

    return DocumentListItem(
        id=str(row["id"]),
        filename=row.get("filename") or "",
        document_type=doc_type,
        file_size_bytes=int(row.get("file_size_bytes") or 0),
        content_type=row.get("content_type") or "application/octet-stream",
        tender_id=row.get("tender_id"),
        transaction_date=row.get("transaction_date"),
        uploaded_at=uploaded_parsed,
    )


@router.get(
    "",
    response_model=list[DocumentListItem],
    summary="List uploaded documents (optionally filtered by transaction date window)",
)
async def list_documents(
    start_date: Optional[date] = Query(
        None,
        description="When set together with end_date, only documents with transaction_date in range.",
    ),
    end_date: Optional[date] = Query(None, description="Inclusive end of transaction_date window."),
) -> list[DocumentListItem]:
    if (start_date is None) ^ (end_date is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide both start_date and end_date, or neither.",
        )
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must be on or before end_date.",
        )

    use_window = start_date is not None and end_date is not None
    sd = str(start_date) if use_window else None
    ed = str(end_date) if use_window else None

    try:
        rows = await data_service.list_documents(start_date=sd, end_date=ed)
        return [_row_to_item(r) for r in rows]
    except Exception as exc:
        logger.error("Failed to list documents: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not retrieve documents.",
        ) from exc
