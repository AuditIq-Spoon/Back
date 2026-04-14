"""
GET  /tenders       — List all tenders (Appels d'Offre).
GET  /tenders/{id}  — Get a single tender with full detail.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from ..core import data_service
from ..models.schemas import Tender

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tenders", tags=["tenders"])


@router.get(
    "",
    response_model=list[Tender],
    summary="List all tenders / Appels d'Offre",
)
async def list_tenders() -> list[Tender]:
    rows = await data_service.list_tenders()
    return [Tender(**row) for row in rows]


@router.get(
    "/{tender_id}",
    response_model=Tender,
    summary="Get a single tender by ID",
)
async def get_tender(tender_id: str) -> Tender:
    row = await data_service.get_tender(tender_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tender '{tender_id}' not found.",
        )
    return Tender(**row)
