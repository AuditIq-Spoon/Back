"""
Pydantic schemas — the single source of truth for all request/response shapes.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class AuditType(str, Enum):
    INOUT = "INOUT"
    TENDER = "TENDER"


class SessionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class DocumentType(str, Enum):
    INVOICE = "INVOICE"
    BANK_STATEMENT = "BANK_STATEMENT"
    QUOTE = "QUOTE"
    PRICE_BOOK = "PRICE_BOOK"
    BID = "BID"
    MARKET_PLACE = "MARKET_PLACE"
    OTHER = "OTHER"


class TenderStatus(str, Enum):
    OPEN = "OPEN"
    AWARDED = "AWARDED"
    CANCELLED = "CANCELLED"


# ---------------------------------------------------------------------------
# Document models
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tender models
# ---------------------------------------------------------------------------

class TenderWinner(BaseModel):
    company: str
    amount: float
    awarded_at: str  # ISO datetime string


class Tender(BaseModel):
    """A procurement tender (Appel d'Offre)."""
    id: str
    reference: str
    name: str
    description: str
    budget: float
    currency: str = "MAD"
    status: TenderStatus
    deadline: Optional[str] = None
    winner: Optional[TenderWinner] = None
    created_at: str


# ---------------------------------------------------------------------------
# Document models
# ---------------------------------------------------------------------------

class DocumentUpload(BaseModel):
    """Metadata returned to the frontend after a successful file upload."""
    id: UUID
    filename: str
    document_type: DocumentType
    file_size_bytes: int
    content_type: str
    tender_id: Optional[str] = None
    transaction_date: Optional[str] = Field(
        None,
        description="Business date inferred from OCR (YYYY-MM-DD), used for INOUT audit date windows.",
    )
    extracted_json: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured JSON produced by the OCR service.",
    )
    uploaded_at: datetime


class DocumentListItem(BaseModel):
    """Lightweight document row for library / audit document lists (no full OCR JSON)."""
    id: str
    filename: str
    document_type: DocumentType
    file_size_bytes: int
    content_type: str
    tender_id: Optional[str] = None
    transaction_date: Optional[str] = Field(
        None, description="YYYY-MM-DD — documents in an INOUT audit window match this range."
    )
    uploaded_at: datetime


class DocumentRecord(BaseModel):
    """Full DB record shape used internally."""
    id: UUID
    filename: str
    document_type: DocumentType
    file_size_bytes: int
    content_type: str
    extracted_json: dict[str, Any]
    uploaded_at: datetime
    tender_id: Optional[str] = None
    project_name: Optional[str] = None
    transaction_date: Optional[str] = None


# ---------------------------------------------------------------------------
# Audit Session models
# ---------------------------------------------------------------------------

class INOUTParams(BaseModel):
    """Parameters specific to an INOUT Transaction Audit."""
    audit_type: Literal[AuditType.INOUT] = AuditType.INOUT
    start_date: date = Field(..., description="Start of the transaction window.")
    end_date: date = Field(..., description="End of the transaction window.")

    @field_validator("end_date")
    @classmethod
    def end_must_be_after_start(cls, end: date, info: Any) -> date:
        start = info.data.get("start_date")
        if start and end <= start:
            raise ValueError("end_date must be strictly after start_date.")
        return end


class TenderParams(BaseModel):
    """Parameters specific to a Tender Audit."""
    audit_type: Literal[AuditType.TENDER] = AuditType.TENDER
    tender_id: Optional[str] = Field(None, description="ID of the related Tender record.")
    project_name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        description="Display name of the tender project.",
    )


# Discriminated union — Pydantic selects the correct model based on audit_type
AuditSessionParams = Union[INOUTParams, TenderParams]


class AuditSessionCreate(BaseModel):
    """
    Request body for POST /sessions.
    Wraps the discriminated union and exposes it under 'params'.
    """
    params: AuditSessionParams = Field(..., discriminator="audit_type")


class AuditSession(BaseModel):
    """Full session record returned to the frontend."""
    id: UUID
    audit_type: AuditType
    status: SessionStatus
    params: dict[str, Any]
    risk_score: Optional[int] = Field(
        None, ge=0, le=100, description="0 = Safe, 100 = Critical Fraud Risk."
    )
    risk_summary: Optional[str] = None
    anomalies: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    completed_at: Optional[datetime] = None


class AuditSessionListItem(BaseModel):
    """Lightweight projection used on the dashboard list."""
    id: UUID
    audit_type: AuditType
    status: SessionStatus
    risk_score: Optional[int] = None
    risk_summary: Optional[str] = None
    params: dict[str, Any]
    created_at: datetime


# ---------------------------------------------------------------------------
# Risk / Result models (from n8n)
# ---------------------------------------------------------------------------

class AnomalyFlag(BaseModel):
    """A single detected anomaly produced by the n8n AI engine."""
    code: str = Field(..., description="Machine-readable anomaly code, e.g. OVERBILLING.")
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    description: str
    affected_documents: list[str] = Field(
        default_factory=list,
        description="Filenames or document IDs implicated in this anomaly.",
    )
    delta_amount: Optional[float] = Field(
        None, description="Monetary difference detected, if applicable."
    )


class RiskResult(BaseModel):
    """
    Payload sent by n8n to POST /webhook/n8n-result.
    Contains the final risk score and all anomaly flags.
    """
    session_id: UUID
    risk_score: int = Field(..., ge=0, le=100)
    risk_summary: str = Field(
        ..., description="One-paragraph plain-text explanation for the human auditor."
    )
    anomalies: list[AnomalyFlag] = Field(default_factory=list)
    processing_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional metadata from the n8n execution (node timings, LLM model used, etc.).",
    )


# ---------------------------------------------------------------------------
# WebSocket progress messages
# ---------------------------------------------------------------------------

class ProgressStep(BaseModel):
    """A single progress event streamed over the WebSocket."""
    session_id: str
    step: int
    total_steps: int
    label: str
    detail: Optional[str] = None
    status: Literal["PENDING", "RUNNING", "DONE", "ERROR"] = "RUNNING"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Generic API responses
# ---------------------------------------------------------------------------

class APIResponse(BaseModel):
    success: bool = True
    message: str = "OK"
    data: Optional[Any] = None


class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    detail: Optional[Any] = None
