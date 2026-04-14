"""
OCR Service — extracts structured JSON from uploaded financial documents.

Currently ships a mock implementation that returns realistic fixture data
based on the detected MIME type / filename. Swap out `_mock_extract` with
a real OCR provider (Google Document AI, AWS Textract, etc.) by reading
the OCR_PROVIDER env variable and routing accordingly.
"""
from __future__ import annotations

import asyncio
import re
from datetime import date, timedelta
from typing import Any

from fastapi import UploadFile

from ..core.config import get_settings
from ..models.schemas import DocumentType


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def extract(file: UploadFile) -> tuple[DocumentType, dict[str, Any]]:
    """
    Reads an uploaded file, infers its document type, and returns
    (document_type, extracted_json).

    All I/O is performed asynchronously so it never blocks the event loop.
    """
    settings = get_settings()
    raw_bytes = await file.read()
    # Reset the cursor so callers can re-read the file if needed
    await file.seek(0)

    doc_type = _infer_document_type(file.filename or "", file.content_type or "")

    if settings.OCR_PROVIDER == "mock":
        extracted = await asyncio.to_thread(_mock_extract, doc_type, file.filename or "")
    else:
        # Plug real OCR provider here
        extracted = await asyncio.to_thread(_mock_extract, doc_type, file.filename or "")

    return doc_type, extracted


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _infer_document_type(filename: str, content_type: str) -> DocumentType:
    """
    Lightweight heuristic that classifies a document based on its name.
    Production systems should inspect the extracted text instead.
    """
    lower = filename.lower()
    if any(k in lower for k in ("invoice", "facture", "inv_")):
        return DocumentType.INVOICE
    if any(k in lower for k in ("bank", "statement", "releve", "rib")):
        return DocumentType.BANK_STATEMENT
    if any(k in lower for k in ("quote", "devis", "quotation", "offer")):
        return DocumentType.QUOTE
    if any(k in lower for k in ("pricebook", "price_book", "catalogue", "tarif")):
        return DocumentType.PRICE_BOOK
    if any(k in lower for k in ("bid", "soumission", "appel")):
        return DocumentType.BID
    if any(k in lower for k in ("market", "marketplace", "comparatif")):
        return DocumentType.MARKET_PLACE
    return DocumentType.OTHER


def _mock_extract(doc_type: DocumentType, filename: str) -> dict[str, Any]:
    """
    Returns deterministic fixture data that mirrors real extraction output.
    Fixtures are designed to demonstrate the SURFACTURATION + DOUBLE PAYMENT
    use-case from the AuditIQ documentation.
    """
    today = date.today()
    base_amount = 10_000.00

    fixtures: dict[DocumentType, dict[str, Any]] = {
        DocumentType.QUOTE: {
            "document_type": "QUOTE",
            "vendor": "Tech Solutions SARL",
            "client": "Municipality of Casablanca",
            "quote_number": "QT-2024-0042",
            "quote_date": str(today - timedelta(days=30)),
            "valid_until": str(today + timedelta(days=60)),
            "currency": "MAD",
            "line_items": [
                {
                    "description": "Software License — Enterprise tier",
                    "quantity": 1,
                    "unit_price": base_amount,
                    "total": base_amount,
                }
            ],
            "subtotal": base_amount,
            "tax_rate": 0.20,
            "tax_amount": base_amount * 0.20,
            "total_amount": base_amount * 1.20,
        },
        DocumentType.INVOICE: {
            "document_type": "INVOICE",
            "vendor": "Tech Solutions SARL",
            "client": "Municipality of Casablanca",
            "invoice_number": "INV-2024-0105",
            "invoice_date": str(today - timedelta(days=15)),
            "due_date": str(today + timedelta(days=15)),
            "currency": "MAD",
            "line_items": [
                {
                    "description": "Software License — Enterprise tier",
                    "quantity": 1,
                    # Overbilling: +20 % above the quoted price
                    "unit_price": base_amount * 1.20,
                    "total": base_amount * 1.20,
                }
            ],
            "subtotal": base_amount * 1.20,
            "tax_rate": 0.20,
            "tax_amount": base_amount * 1.20 * 0.20,
            "total_amount": base_amount * 1.20 * 1.20,
            "_audit_note": "Amount is 20% above the approved quote.",
        },
        DocumentType.BANK_STATEMENT: {
            "document_type": "BANK_STATEMENT",
            "account_holder": "Municipality of Casablanca",
            "bank": "Attijariwafa Bank",
            "iban": "MA64 0110 0013 0000 2060 002",
            "period_start": str(today - timedelta(days=30)),
            "period_end": str(today),
            "currency": "MAD",
            "transactions": [
                {
                    "date": str(today - timedelta(days=10)),
                    "description": "Virement Tech Solutions SARL — INV-2024-0105",
                    "debit": base_amount * 1.20 * 1.20,
                    "credit": 0,
                    "balance": 500_000 - base_amount * 1.20 * 1.20,
                },
                {
                    "date": str(today - timedelta(days=9)),
                    # Duplicate payment — same reference, next day
                    "description": "Virement Tech Solutions SARL — INV-2024-0105",
                    "debit": base_amount * 1.20 * 1.20,
                    "credit": 0,
                    "balance": 500_000 - base_amount * 1.20 * 1.20 * 2,
                    "_audit_note": "DUPLICATE: Same invoice reference paid twice.",
                },
            ],
            "opening_balance": 500_000,
            "closing_balance": 500_000 - base_amount * 1.20 * 1.20 * 2,
        },
        DocumentType.PRICE_BOOK: {
            "document_type": "PRICE_BOOK",
            "vendor": "Tech Solutions SARL",
            "effective_date": str(today - timedelta(days=90)),
            "currency": "MAD",
            "items": [
                {
                    "sku": "SW-ENT-001",
                    "description": "Software License — Enterprise tier",
                    "list_price": base_amount,
                    "currency": "MAD",
                }
            ],
        },
        DocumentType.BID: {
            "document_type": "BID",
            "bidder": "Tech Solutions SARL",
            "project": re.sub(r"[^a-zA-Z0-9 ]", "", filename).strip() or "Project Appel d'Offre",
            "submission_date": str(today - timedelta(days=45)),
            "bid_amount": base_amount * 0.95,
            "currency": "MAD",
            "validity_days": 90,
            "technical_score": 82,
            "financial_score": 91,
        },
        DocumentType.MARKET_PLACE: {
            "document_type": "MARKET_PLACE",
            "project": re.sub(r"[^a-zA-Z0-9 ]", "", filename).strip() or "Project Appel d'Offre",
            "market_analysis_date": str(today - timedelta(days=50)),
            "competing_offers": [
                {"vendor": "Tech Solutions SARL", "amount": base_amount * 0.95},
                {"vendor": "Digital Corp MA", "amount": base_amount * 1.05},
                {"vendor": "Innova Tech", "amount": base_amount * 1.10},
            ],
            "recommended_vendor": "Tech Solutions SARL",
            "recommendation_rationale": "Best price-quality ratio.",
        },
        DocumentType.OTHER: {
            "document_type": "OTHER",
            "raw_text": f"Mock extraction for unclassified document: {filename}",
        },
    }

    return fixtures.get(doc_type, fixtures[DocumentType.OTHER])
