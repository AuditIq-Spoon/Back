"""
DataService — unified data-access layer.

Routes to the in-memory mock_db when Supabase is not configured,
and to Supabase when it is. All callers go through this module so
switching to a real database requires changing only this file.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from .config import get_settings

logger = logging.getLogger(__name__)


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
    resp = await asyncio.to_thread(
        lambda: sb.table("documents").insert(record).execute()
    )
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
