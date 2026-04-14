"""
Supabase client factory.

We use the supabase-py async client so every DB call can be awaited
inside FastAPI's async route handlers.
"""
from supabase import create_client, Client
from functools import lru_cache
from .config import get_settings


@lru_cache()
def get_supabase() -> Client:
    """
    Returns a cached synchronous Supabase client.

    NOTE: supabase-py v2 ships with an AsyncClient as well.
    For this project we wrap calls with asyncio.to_thread() in services
    so the FastAPI event loop is never blocked.
    """
    settings = get_settings()
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
