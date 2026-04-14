"""
Mock in-memory database — seeded with realistic tender & document fixtures.

TO REMOVE: delete this file and update data_service.py to always use Supabase.
"""
from __future__ import annotations

import copy
from datetime import datetime, date, timedelta
from typing import Any

# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

today = date.today()

MOCK_TENDERS: list[dict[str, Any]] = [
    {
        "id": "tender-001",
        "reference": "AO-2024-001",
        "name": "IT Infrastructure Upgrade",
        "description": (
            "Supply and installation of servers, networking equipment, and workstations "
            "for all municipal buildings."
        ),
        "budget": 950_000.0,
        "currency": "MAD",
        "status": "AWARDED",
        "deadline": "2024-03-31",
        "winner": {
            "company": "Tech Solutions SARL",
            "amount": 910_000.0,
            "awarded_at": "2024-04-10T10:00:00",
        },
        "created_at": "2024-01-15T08:00:00",
    },
    {
        "id": "tender-002",
        "reference": "AO-2024-002",
        "name": "Office Supplies & Stationery Q1 2025",
        "description": "Annual procurement of office supplies for all municipal departments.",
        "budget": 45_000.0,
        "currency": "MAD",
        "status": "AWARDED",
        "deadline": "2024-11-30",
        "winner": {
            "company": "Bureau Plus MA",
            "amount": 38_500.0,
            "awarded_at": "2024-12-05T09:30:00",
        },
        "created_at": "2024-10-01T08:00:00",
    },
    {
        "id": "tender-003",
        "reference": "AO-2024-003",
        "name": "Security System Upgrade — Municipal Campus",
        "description": (
            "Design, supply, and installation of CCTV, access control, "
            "and alarm systems across all campus buildings."
        ),
        "budget": 300_000.0,
        "currency": "MAD",
        "status": "AWARDED",
        "deadline": "2024-06-15",
        "winner": {
            "company": "SecureIT Maroc",
            "amount": 275_000.0,
            "awarded_at": "2024-07-01T11:00:00",
        },
        "created_at": "2024-04-01T08:00:00",
    },
    {
        "id": "tender-004",
        "reference": "AO-2025-001",
        "name": "Fleet Vehicle Maintenance 2025",
        "description": "Maintenance and repair services for the municipal vehicle fleet (42 vehicles).",
        "budget": 180_000.0,
        "currency": "MAD",
        "status": "OPEN",
        "deadline": str(today + timedelta(days=45)),
        "winner": None,
        "created_at": "2025-01-10T08:00:00",
    },
    {
        "id": "tender-005",
        "reference": "AO-2025-002",
        "name": "Waste Management & Street Cleaning Services",
        "description": "Outsourcing of waste collection, sorting, and street cleaning operations.",
        "budget": 1_200_000.0,
        "currency": "MAD",
        "status": "OPEN",
        "deadline": str(today + timedelta(days=75)),
        "winner": None,
        "created_at": "2025-01-20T08:00:00",
    },
    {
        "id": "tender-006",
        "reference": "AO-2024-004",
        "name": "Municipal Website Redesign",
        "description": "Complete redesign of the municipal website and citizen portal.",
        "budget": 120_000.0,
        "currency": "MAD",
        "status": "CANCELLED",
        "deadline": "2024-09-30",
        "winner": None,
        "created_at": "2024-07-01T08:00:00",
    },
]

_DOCUMENTS: list[dict[str, Any]] = []
_SESSIONS: list[dict[str, Any]] = []

# ---------------------------------------------------------------------------
# Tenders
# ---------------------------------------------------------------------------

def list_tenders() -> list[dict]:
    return [copy.deepcopy(t) for t in MOCK_TENDERS]


def get_tender(tender_id: str) -> dict | None:
    for t in MOCK_TENDERS:
        if t["id"] == tender_id:
            return copy.deepcopy(t)
    return None

# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def list_sessions() -> list[dict]:
    return sorted(
        [copy.deepcopy(s) for s in _SESSIONS],
        key=lambda s: s.get("created_at", ""),
        reverse=True,
    )


def get_session(session_id: str) -> dict | None:
    for s in _SESSIONS:
        if s["id"] == session_id:
            return copy.deepcopy(s)
    return None


def create_session(record: dict) -> dict:
    _SESSIONS.append(copy.deepcopy(record))
    return copy.deepcopy(record)


def update_session(session_id: str, data: dict) -> None:
    for s in _SESSIONS:
        if s["id"] == session_id:
            s.update(data)
            return

# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

def list_documents(
    types: list[str] | None = None,
    tender_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    docs = [copy.deepcopy(d) for d in _DOCUMENTS]
    if types:
        docs = [d for d in docs if d.get("document_type") in types]
    if tender_id:
        docs = [d for d in docs if d.get("tender_id") == tender_id]
    if start_date:
        docs = [d for d in docs if (d.get("transaction_date") or "") >= start_date]
    if end_date:
        docs = [d for d in docs if (d.get("transaction_date") or "") <= end_date]
    docs.sort(key=lambda d: d.get("uploaded_at") or "", reverse=True)
    return docs


def create_document(record: dict) -> dict:
    _DOCUMENTS.append(copy.deepcopy(record))
    return copy.deepcopy(record)
