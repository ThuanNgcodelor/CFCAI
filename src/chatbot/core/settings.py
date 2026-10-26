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
    DATABASE_URL: str | None = None
    INBOX_BACKEND: str = "memory"

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_URL: str | None = None

    # Ollama LLM
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL_TAG: str = "qwen2.5:7b"
    OLLAMA_TIMEOUT_SECONDS: float = 15.0
    OLLAMA_MAX_ATTEMPTS: int = 2
    INTENT_PROMPT_PATH: str = "config/prompts/intent.md"
    INTENT_NORMALIZATION_PATH: str = "config/normalization/vi_intent.json"

    # Meta Messenger - CFC
    CFC_PAGE_ID: str = ""
    CFC_VERIFY_TOKEN: str = ""
    CFC_APP_SECRET: str = ""
    CFC_PAGE_ACCESS_TOKEN: str = ""

    # Meta Messenger - ZEO
    ZEO_PAGE_ID: str = ""
    ZEO_VERIFY_TOKEN: str = ""
    ZEO_APP_SECRET: str = ""
    ZEO_PAGE_ACCESS_TOKEN: str = ""

    # Messaging
    DEBOUNCE_SECONDS: float = 5.0
    MAX_BATCH_SECONDS: float = 20.0
    META_SEND_ENABLED: bool = False
    META_TEST_RECIPIENT_ID: str = ""

    # MISA AMIS CRM
    AMIS_BASE_URL: str = "https://crmconnect.misa.vn/api/v2"
    AMIS_CLIENT_ID: str = "JavisCFCChatbot"
    AMIS_CLIENT_SECRET: str = ""
    AMIS_SYNC_INTERNAL_TOKEN: str = ""
    AMIS_PILOT_APPROVE_ALL: bool = False

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    def get_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    def get_redis_url(self) -> str:
        if self.REDIS_URL:
            return self.REDIS_URL
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    def validate_production_secrets(self) -> None:
        """Fail closed before production starts with placeholder secrets."""
        if self.ENVIRONMENT.lower() not in {"production", "prod", "staging"}:
            return
        required = {
            "CFC_PAGE_ID": self.CFC_PAGE_ID,
            "CFC_VERIFY_TOKEN": self.CFC_VERIFY_TOKEN,
            "CFC_APP_SECRET": self.CFC_APP_SECRET,
            "CFC_PAGE_ACCESS_TOKEN": self.CFC_PAGE_ACCESS_TOKEN,
            "ZEO_PAGE_ID": self.ZEO_PAGE_ID,
            "ZEO_VERIFY_TOKEN": self.ZEO_VERIFY_TOKEN,
            "ZEO_APP_SECRET": self.ZEO_APP_SECRET,
            "ZEO_PAGE_ACCESS_TOKEN": self.ZEO_PAGE_ACCESS_TOKEN,
            "AMIS_SYNC_INTERNAL_TOKEN": self.AMIS_SYNC_INTERNAL_TOKEN,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(
                "Production secrets/configuration missing: " + ", ".join(missing)
            )
        if self.INBOX_BACKEND.lower() != "postgres":
            raise ValueError("Production requires INBOX_BACKEND=postgres")


settings = Settings()
settings.validate_production_secrets()
