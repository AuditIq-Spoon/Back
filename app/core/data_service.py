"""
DataService — unified data-access layer.

Routes to the in-memory mock_db when Supabase is not configured,
and to Supabase when it is. All callers go through this module so
switching to a real database requires changing only this file.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
from typing import Any

from .config import get_settings

logger = logging.getLogger(__name__)

def _sanitize_json_value(obj: Any) -> Any:
    """Ensure values are JSON-compatible (Postgres JSONB rejects NaN / Infinity)."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {str(k): _sanitize_json_value(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_json_value(v) for v in obj]
    return obj


_ALLOWED_DOCUMENT_KEYS = frozenset(
    {
        "id",
        "filename",
        "document_type",
        "file_size_bytes",
        "content_type",
        "extracted_json",
        "uploaded_at",
        "transaction_date",
        "project_name",
        "tender_id",
    },
)


def _document_row_for_supabase(record: dict[str, Any]) -> dict[str, Any]:
    """JSON-safe row with only columns that exist on public.documents."""
    rec = dict(record)
    if "extracted_json" in rec and isinstance(rec["extracted_json"], dict):
        rec["extracted_json"] = _sanitize_json_value(rec["extracted_json"])
    try:
        safe = json.loads(json.dumps(rec, default=str, allow_nan=False))
    except (TypeError, ValueError) as exc:
        logger.warning("Document JSON round-trip failed, stripping non-finite floats: %s", exc)
        rec["extracted_json"] = _sanitize_json_value(rec.get("extracted_json") or {})
        safe = json.loads(json.dumps(rec, default=str, allow_nan=False))

    row = {k: safe[k] for k in _ALLOWED_DOCUMENT_KEYS if k in safe}
    fn = row.get("filename")
    if not fn or not str(fn).strip():
        row["filename"] = "unnamed"
    ct = row.get("content_type")
    if not ct or not str(ct).strip():
        row["content_type"] = "application/octet-stream"

    ej = row.get("extracted_json")
    if isinstance(ej, str):
        row["extracted_json"] = json.loads(ej)
    elif ej is None:
        row["extracted_json"] = {}
    if row.get("tender_id") in ("", None):
        row.pop("tender_id", None)
    return row


def _insert_document_row(sb: Any, insert_row: dict[str, Any]) -> Any:
    """Sync helper for asyncio.to_thread (avoids closure pitfalls)."""
    return sb.table("documents").insert(insert_row).execute()


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

async def create_session(record: dict) -> dict:
    if get_settings().use_mock_db:
        from . import mock_db
        return mock_db.create_session(record)
    sb = _sb()
    resp = await asyncio.to_thread(
        lambda: sb.table("audit_sessions").insert(record).execute()
    )
    return resp.data[0]


async def get_session(session_id: str) -> dict | None:
    if get_settings().use_mock_db:
        from . import mock_db
        return mock_db.get_session(session_id)
    sb = _sb()
    resp = await asyncio.to_thread(
        lambda: sb.table("audit_sessions")
        .select("*")
        .eq("id", session_id)
        .single()
        .execute()
    )
    return resp.data


async def update_session(session_id: str, data: dict) -> None:
    if get_settings().use_mock_db:
        from . import mock_db
        return mock_db.update_session(session_id, data)
    sb = _sb()
    await asyncio.to_thread(
        lambda: sb.table("audit_sessions").update(data).eq("id", session_id).execute()
    )


async def list_sessions() -> list[dict]:
    if get_settings().use_mock_db:
        from . import mock_db
        return mock_db.list_sessions()
    sb = _sb()
    resp = await asyncio.to_thread(
        lambda: sb.table("audit_sessions")
        .select("id, audit_type, status, risk_score, risk_summary, params, created_at")
        .order("created_at", desc=True)
        .execute()
    )
    return resp.data or []


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

async def create_document(record: dict) -> dict:
    if get_settings().use_mock_db:
        from . import mock_db
        return mock_db.create_document(record)
    sb = _sb()
    row = _document_row_for_supabase(record)
    try:
        resp = await asyncio.to_thread(_insert_document_row, sb, row)
    except Exception as exc:
        logger.exception(
            "Supabase documents.insert failed id=%s filename=%s: %s",
            row.get("id"),
            row.get("filename"),
            exc,
        )
        raise
    if not resp.data:
        logger.error("Supabase insert returned empty data for document id=%s", row.get("id"))
        raise RuntimeError("Supabase insert returned no row")
    return resp.data[0]


async def list_documents(
    types: list[str] | None = None,
    tender_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    if get_settings().use_mock_db:
        from . import mock_db
        return mock_db.list_documents(
            types=types, tender_id=tender_id,
            start_date=start_date, end_date=end_date,
        )
    sb = _sb()
    query = sb.table("documents").select("*")
    if types:
        query = query.in_("document_type", types)
    if tender_id:
        query = query.eq("tender_id", tender_id)
    if start_date:
        query = query.gte("transaction_date", start_date)
    if end_date:
        query = query.lte("transaction_date", end_date)
    query = query.order("uploaded_at", desc=True)
    resp = await asyncio.to_thread(lambda: query.execute())
    return resp.data or []


# ---------------------------------------------------------------------------
# Tenders
# ---------------------------------------------------------------------------

async def list_tenders() -> list[dict]:
    if get_settings().use_mock_db:
        from . import mock_db
        return mock_db.list_tenders()
    sb = _sb()
    resp = await asyncio.to_thread(
        lambda: sb.table("tenders").select("*").order("created_at", desc=True).execute()
    )
    rows = resp.data or []
    if not rows:
        # Supabase project often has no seed rows yet; keep UI usable.
        logger.info("tenders table is empty — returning built-in fixture tenders")
        from . import mock_db
        return mock_db.list_tenders()
    return rows


async def get_tender(tender_id: str) -> dict | None:
    if get_settings().use_mock_db:
        from . import mock_db
        return mock_db.get_tender(tender_id)
    sb = _sb()
    resp = await asyncio.to_thread(
        lambda: sb.table("tenders").select("*").eq("id", tender_id).maybe_single().execute()
    )
    row = resp.data
    if isinstance(row, dict) and row.get("id"):
        return row
    from . import mock_db
    return mock_db.get_tender(tender_id)


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _sb():
    from .database import get_supabase
    return get_supabase()
