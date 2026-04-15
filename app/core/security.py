"""
Security utilities.

Provides a simple dependency that validates the shared n8n callback secret
so only n8n can post results to /webhook/n8n-result.
"""
from fastapi import Header, HTTPException, status
from .config import get_settings


async def verify_n8n_secret(
    x_n8n_secret: str = Header(default=""),
    authorization: str = Header(default=""),
) -> None:
    """
    FastAPI dependency injected on the n8n result webhook endpoint.
    Skipped when N8N_SECRET is empty.

    Accepts ``X-N8n-Secret: <secret>`` (same header AuditIQ sends to n8n) or
    ``Authorization: Bearer <secret>`` if the HTTP Request node is configured that way.
    """
    settings = get_settings()
    expected = (settings.N8N_SECRET or "").strip()
    if not expected:
        return
    if x_n8n_secret == expected:
        return
    auth = (authorization or "").strip()
    if auth.lower().startswith("bearer ") and auth[7:].strip() == expected:
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid n8n secret (use X-N8n-Secret or Authorization: Bearer).",
    )
