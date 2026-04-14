"""
AuditIQ — FastAPI Application Entry Point.

Run locally:
    uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .core.config import get_settings
from .api import upload, sessions, websocket, webhook, tenders, documents

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "AuditIQ — Intelligent Financial & Procurement Auditing Platform. "
        "Orchestrates OCR extraction, AI-driven risk scoring, and real-time "
        "progress streaming for financial document audits."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url)
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": "Internal server error.", "detail": str(exc)},
    )

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(upload.router, prefix=settings.API_PREFIX)
app.include_router(documents.router, prefix=settings.API_PREFIX)
app.include_router(sessions.router, prefix=settings.API_PREFIX)
app.include_router(tenders.router, prefix=settings.API_PREFIX)
app.include_router(webhook.router, prefix=settings.API_PREFIX)
app.include_router(websocket.router)   # WebSocket has no API prefix


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["health"], summary="Health check")
async def health() -> dict:
    doc_url = (settings.N8N_WEBHOOK_DOCUMENT_UPLOAD_URL or "").strip()
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "integrations": {
            "n8n_document_upload_webhook_configured": bool(doc_url),
            "n8n_upload_workflow_id": settings.N8N_UPLOAD_WORKFLOW_ID,
        },
    }


# ---------------------------------------------------------------------------
# Startup / shutdown events
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def on_startup() -> None:
    logger.info("AuditIQ API started — version %s", settings.APP_VERSION)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    logger.info("AuditIQ API shutting down.")
