"""
Security utilities.

Provides a simple dependency that validates the shared n8n callback secret
so only n8n can post results to /webhook/n8n-result.
"""
from fastapi import Header, HTTPException, status
from .config import get_settings


async def verify_n8n_secret(x_n8n_secret: str = Header(default="")) -> None:
    """
    FastAPI dependency injected on the n8n result webhook endpoint.
    Skipped in development when N8N_SECRET is empty.
    """
    settings = get_settings()
    if settings.N8N_SECRET and x_n8n_secret != settings.N8N_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid n8n secret header.",
        )
