"""
POST /upload — Accepts one or more files with optional document-type overrides
               and tender assignments, runs OCR, stores metadata, and triggers n8n.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from typing import Annotated, Any, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status

from ..core import data_service
from ..models.schemas import DocumentType, DocumentUpload
from ..services import n8n_service, ocr_service
from ..services.upload_n8n_result_store import mark_pending

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/upload", tags=["documents"])

MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
}


@router.post(
    "",
    response_model=list[DocumentUpload],
    status_code=status.HTTP_201_CREATED,
    summary="Upload financial documents with optional type overrides",
)
async def upload_documents(
    background_tasks: BackgroundTasks,
    files: Annotated[list[UploadFile], File(description="One or more financial documents.")],
    document_types: Annotated[
        Optional[str],
        Form(description="Comma-separated DocumentType values matching file order. Auto-inferred if omitted."),
    ] = None,
    tender_ids: Annotated[
        Optional[str],
        Form(description="Comma-separated tender IDs (or empty strings) matching file order."),
    ] = None,
) -> list[DocumentUpload]:
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one file must be provided.",
        )

    _validate_files(files)

    type_overrides = _parse_list(document_types, len(files))
    tid_list = _parse_list(tender_ids, len(files))

    tasks = [
        _process_single_file(f, type_overrides[i], tid_list[i] or None)
        for i, f in enumerate(files)
    ]
    tuples = await asyncio.gather(*tasks)

    uploads: list[DocumentUpload] = []
    for doc_upload, record in tuples:
        uploads.append(doc_upload)
        background_tasks.add_task(_safe_trigger_document_n8n, record)

    return uploads


@router.get(
    "/n8n-status/{document_id}",
    summary="Poll n8n upload workflow result (yhs1QhteOspEbuDN callback stored server-side)",
)
async def upload_n8n_status(document_id: str) -> dict[str, Any]:
    from ..services.upload_n8n_result_store import get_result

    stored = get_result(document_id)
    if not stored:
        return {"status": "pending", "document_id": document_id}
    if stored.get("status") == "ready" or "risk_score" in stored:
        return {"status": "ready", "document_id": document_id, "result": stored}
    return {"status": "pending", "document_id": document_id}


async def _safe_trigger_document_n8n(record: dict[str, Any]) -> None:
    """Runs after the upload response is sent; logs any crash so n8n failures are visible."""
    try:
        await n8n_service.trigger_document_upload(record)
    except Exception:
        logger.exception(
            "Background n8n document task crashed for document_id=%s",
            record.get("id"),
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_files(files: list[UploadFile]) -> None:
    for f in files:
        if f.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=(
                    f"File '{f.filename}' has unsupported content type '{f.content_type}'. "
                    f"Allowed: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}"
                ),
            )


def _parse_list(raw: str | None, count: int) -> list[str]:
    if not raw:
        return [""] * count
    parts = [p.strip() for p in raw.split(",")]
    while len(parts) < count:
        parts.append("")
    return parts[:count]


def _transaction_date_from_extracted(doc_type: DocumentType, extracted: dict[str, Any]) -> str:
    """
    Derive a YYYY-MM-DD business date from OCR JSON for INOUT audit window matching.
    """
    keys = (
        "invoice_date",
        "quote_date",
        "submission_date",
        "market_analysis_date",
        "period_start",
        "effective_date",
    )
    for k in keys:
        v = extracted.get(k)
        if isinstance(v, str) and len(v) >= 10:
            return v[:10]
    return date.today().isoformat()


async def _process_single_file(
    file: UploadFile,
    doc_type_override: str,
    tender_id: str | None,
) -> tuple[DocumentUpload, dict[str, Any]]:
    doc_id = uuid4()

    raw = await file.read()
    if len(raw) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File '{file.filename}' exceeds the 20 MB limit.",
        )
    await file.seek(0)

    inferred_type, extracted_json = await ocr_service.extract(file)

    doc_type = inferred_type
    if doc_type_override:
        try:
            doc_type = DocumentType(doc_type_override)
        except ValueError:
            logger.warning("Unknown document_type override '%s', keeping inferred.", doc_type_override)

    txn_date = _transaction_date_from_extracted(doc_type, extracted_json)
    now = datetime.now(timezone.utc)

    safe_name = (file.filename or "").strip() or "unnamed"
    safe_ct = (file.content_type or "").strip() or "application/octet-stream"

    record: dict[str, Any] = {
        "id": str(doc_id),
        "filename": safe_name,
        "document_type": doc_type.value,
        "file_size_bytes": len(raw),
        "content_type": safe_ct,
        "extracted_json": extracted_json,
        "uploaded_at": now.isoformat().replace("+00:00", "Z"),
        "transaction_date": txn_date,
    }
    if tender_id:
        record["tender_id"] = tender_id

    try:
        await data_service.create_document(record)
        mark_pending(str(doc_id))
    except Exception as exc:
        logger.error("DB insert failed for %s: %s", file.filename, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to persist document metadata. Please try again.",
        ) from exc

    du = DocumentUpload(
        id=doc_id,
        filename=file.filename or "unknown",
        document_type=doc_type,
        file_size_bytes=len(raw),
        content_type=file.content_type or "application/octet-stream",
        tender_id=tender_id,
        transaction_date=txn_date,
        extracted_json=extracted_json,
        uploaded_at=now,
    )
    return du, record
