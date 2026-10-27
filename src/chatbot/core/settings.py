# pyrefly: ignore[missing-import]
from datetime import datetime

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"
    # Required to access /admin in staging/production. Development may omit it
    # for local test ergonomics, but the application fails closed before a
    # production process starts without this value.
    ADMIN_API_TOKEN: str = ""
    # Optional `{role: token}` JSON for least-privilege operator accounts.
    # The sole ADMIN_API_TOKEN remains a break-glass administrator credential.
    ADMIN_ROLE_TOKENS_JSON: str = ""

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
    ADMINISTRATIVE_AREAS_PATH: str = "config/normalization/administrative_areas.json"
    MARKDOWN_CATALOG_MAPPING_PATH: str = "config/data_sources/markdown_mapping.json"
    DATA_SOURCE_MANIFEST_PATH: str = "data/sources/manifest.yaml"
    SUPPORT_CONTACTS_PATH: str = "config/business/support_contacts.json"

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
    # Delivery is deliberately disabled unless an operator chooses a mode.
    # `shadow` records/suppresses candidates; `canary` is a deny-by-default
    # allow-list; `live` still needs explicit business approval.
    DELIVERY_MODE: str = "disabled"
    CANARY_PAGE_IDS: str = ""
    CANARY_WORKFLOWS: str = ""
    CANARY_RECIPIENT_IDS: str = ""
    CANARY_PERCENT: int = 0
    CANARY_SEND_APPROVED: bool = False
    LIVE_SEND_APPROVED: bool = False
    # A release fence prevents an old PENDING outbox row from being sent after
    # an operator changes delivery mode. ISO-8601 with a UTC offset is required.
    DELIVERY_NOT_BEFORE: str = ""

    # MISA AMIS CRM
    AMIS_BASE_URL: str = "https://crmconnect.misa.vn/api/v2"
    AMIS_CLIENT_ID: str = "JavisCFCChatbot"
    AMIS_CLIENT_SECRET: str = ""
    AMIS_SYNC_INTERNAL_TOKEN: str = ""
    AMIS_PILOT_APPROVE_ALL: bool = False
    AMIS_SYNC_INTERVAL_SECONDS: int = 3600
    AMIS_SYNC_LOCK_SECONDS: int = 900
    AMIS_SNAPSHOT_RETENTION_SECONDS: int = 604800
    AMIS_SYNC_FRESHNESS_SECONDS: int = 5400

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @field_validator("DEBUG", mode="before")
    @classmethod
    def normalize_debug_value(cls, value: object) -> object:
        """Reject neither a host's release marker nor a valid boolean setting."""
        if isinstance(value, str) and value.strip().casefold() in {
            "release",
            "production",
            "prod",
        }:
            return False
        return value

    def get_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    def get_redis_url(self) -> str:
        if self.REDIS_URL:
            return self.REDIS_URL
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() in {"production", "prod", "staging"}

    def get_delivery_mode(self) -> str:
        mode = self.DELIVERY_MODE.strip().lower()
        if mode not in {"disabled", "shadow", "canary", "live"}:
            raise ValueError(
                "DELIVERY_MODE must be disabled, shadow, canary, or live"
            )
        return mode

    def get_delivery_not_before(self) -> datetime | None:
        raw = self.DELIVERY_NOT_BEFORE.strip()
        if not raw:
            return None
        try:
            value = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise ValueError("DELIVERY_NOT_BEFORE must be ISO-8601 with UTC offset") from exc
        if value.tzinfo is None:
            raise ValueError("DELIVERY_NOT_BEFORE must include a UTC offset")
        return value

    def validate_production_secrets(self) -> None:
        """Fail closed before production starts with placeholder secrets."""
        if not self.is_production():
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
            "ADMIN_API_TOKEN": self.ADMIN_API_TOKEN,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(
                "Production secrets/configuration missing: " + ", ".join(missing)
            )
        if self.INBOX_BACKEND.lower() != "postgres":
            raise ValueError("Production requires INBOX_BACKEND=postgres")
        from src.chatbot.modules.ops.auth import parse_role_tokens

        parse_role_tokens(self.ADMIN_ROLE_TOKENS_JSON)
        mode = self.get_delivery_mode()
        if self.META_SEND_ENABLED and mode == "disabled":
            raise ValueError("META_SEND_ENABLED requires an explicit DELIVERY_MODE")
        if mode == "canary" and not self.CANARY_SEND_APPROVED:
            raise ValueError("Canary delivery requires CANARY_SEND_APPROVED=true")
        if mode == "live" and not self.LIVE_SEND_APPROVED:
            raise ValueError("Live delivery requires LIVE_SEND_APPROVED=true")
        if mode in {"canary", "live"} and self.get_delivery_not_before() is None:
            raise ValueError("Canary/live delivery requires DELIVERY_NOT_BEFORE")


settings = Settings()
settings.validate_production_secrets()
