"""
Application configuration loaded from environment variables.
Uses pydantic-settings for type-safe env parsing.
"""
import re
from functools import lru_cache

from pydantic_settings import BaseSettings

# supabase-py only accepts legacy JWT-style keys (anon / service_role), not newer
# publishable keys (sb_publishable_…). See: create_client() key validation.
_SUPABASE_PY_KEY_PATTERN = re.compile(
    r"^[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*$"
)


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "AuditIQ API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    API_PREFIX: str = "/api"
    API_BASE_URL: str = "http://localhost:8000"

    # Public SPA URL (for n8n payloads / CORS). Example: https://your-app.netlify.app
    FRONTEND_PUBLIC_URL: str = ""

    # CORS — comma-separated origins
    CORS_ORIGINS: str = "http://localhost:4200"

    # Supabase (leave as "mock" to use the in-memory mock database)
    SUPABASE_URL: str = "mock"
    SUPABASE_KEY: str = "mock"

    # n8n (leave as "mock" to skip webhook and return a simulated result)
    N8N_WEBHOOK_INOUT_URL: str = "mock"
    N8N_WEBHOOK_TENDER_URL: str = "mock"
    N8N_SECRET: str = ""

    # n8n — per-file upload processing (Webhook node URL from workflow editor)
    # Workflow reference (shown in n8n URL): …/workflow/yhs1QhteOspEbuDN
    N8N_UPLOAD_WORKFLOW_ID: str = "yhs1QhteOspEbuDN"
    N8N_WEBHOOK_DOCUMENT_UPLOAD_URL: str = ""

    def supabase_key_valid_for_python_client(self) -> bool:
        """True if SUPABASE_KEY is in the form supabase-py accepts (JWT anon or service_role)."""
        k = (self.SUPABASE_KEY or "").strip()
        if not k or k == "mock":
            return False
        return bool(_SUPABASE_PY_KEY_PATTERN.match(k))

    @property
    def use_mock_db(self) -> bool:
        """True when Supabase is not configured or the key cannot be used by supabase-py."""
        if self.SUPABASE_URL in ("mock", "https://your-project.supabase.co", ""):
            return True
        if not self.supabase_key_valid_for_python_client():
            return True
        return False

    @property
    def supabase_configured_but_key_incompatible(self) -> bool:
        """URL looks real but key is missing or not a JWT — explains mock fallback."""
        if self.SUPABASE_URL in ("mock", "https://your-project.supabase.co", ""):
            return False
        return not self.supabase_key_valid_for_python_client()

    @property
    def use_mock_n8n(self) -> bool:
        """True when n8n webhooks are not configured."""
        return self.N8N_WEBHOOK_INOUT_URL in ("mock", "https://your-n8n-instance.com/webhook/auditiq-inout", "")

    # OCR (placeholder — swap with real provider key in production)
    OCR_PROVIDER: str = "mock"  # "mock" | "google" | "aws"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton — call this everywhere instead of instantiating directly."""
    return Settings()
