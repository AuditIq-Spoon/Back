"""
Application configuration loaded from environment variables.
Uses pydantic-settings for type-safe env parsing.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "AuditIQ API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    API_PREFIX: str = "/api"
    API_BASE_URL: str = "http://localhost:8000"

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

    @property
    def use_mock_db(self) -> bool:
        """True when Supabase is not properly configured."""
        return self.SUPABASE_URL in ("mock", "https://your-project.supabase.co", "")

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
