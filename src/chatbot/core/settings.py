from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # App
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # PostgreSQL
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "cfc_zeo_db"
    POSTGRES_USER: str = "cfc_admin"
    POSTGRES_PASSWORD: str = "cfc_secret_password"
    DATABASE_URL: Optional[str] = None

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_URL: Optional[str] = None

    # Ollama LLM
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL_TAG: str = "qwen2.5:7b"
    OLLAMA_TIMEOUT_SECONDS: float = 15.0

    # Meta Messenger - CFC
    CFC_PAGE_ID: str = ""
    CFC_VERIFY_TOKEN: str = "default_cfc_verify"
    CFC_APP_SECRET: str = "default_cfc_secret"
    CFC_PAGE_ACCESS_TOKEN: str = ""

    # Meta Messenger - ZEO
    ZEO_PAGE_ID: str = ""
    ZEO_VERIFY_TOKEN: str = "default_zeo_verify"
    ZEO_APP_SECRET: str = "default_zeo_secret"
    ZEO_PAGE_ACCESS_TOKEN: str = ""

    # Messaging
    DEBOUNCE_SECONDS: float = 5.0
    MAX_BATCH_SECONDS: float = 20.0

    # MISA AMIS CRM
    AMIS_BASE_URL: str = "https://crmconnect.misa.vn/api/v2"
    AMIS_CLIENT_ID: str = "JavisCFCChatbot"
    AMIS_CLIENT_SECRET: str = ""
    AMIS_SYNC_INTERNAL_TOKEN: str = "internal_secret_sync_token"
    AMIS_PILOT_APPROVE_ALL: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def get_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    def get_redis_url(self) -> str:
        if self.REDIS_URL:
            return self.REDIS_URL
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

settings = Settings()
