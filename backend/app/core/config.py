"""Application configuration.

All settings are read from environment variables (optionally via a ``.env``
file).  Nothing here contains production secrets - the credential-encryption
key is mandatory in production and validated at startup.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="HUMISENSE_",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Runtime ---------------------------------------------------------
    environment: str = Field(default="development")
    debug: bool = Field(default=False)
    api_prefix: str = Field(default="/api/v1")

    # --- Database --------------------------------------------------------
    database_url: str = Field(
        default="sqlite+pysqlite:///./humisense.db",
        description="SQLAlchemy URL. PostgreSQL in production.",
    )

    # --- Credential encryption ------------------------------------------
    # 32-byte key, base64 or hex encoded.  Required outside development.
    credential_encryption_key: str | None = Field(default=None)
    credential_key_version: int = Field(default=1)

    # --- Egress / SSRF ---------------------------------------------------
    egress_allow_private: bool = Field(default=False)
    egress_allowed_hosts: list[str] = Field(default_factory=list)
    egress_blocked_hosts: list[str] = Field(default_factory=list)
    egress_connect_timeout_seconds: float = Field(default=10.0)

    # --- Connector runtime ----------------------------------------------
    connector_request_timeout_seconds: float = Field(default=30.0)
    connector_max_retries: int = Field(default=5)
    connector_max_pages: int = Field(default=10_000)
    connector_page_size: int = Field(default=100)

    # --- Sync ------------------------------------------------------------
    sync_batch_size: int = Field(default=500)
    sync_max_retries: int = Field(default=5)
    sync_backoff_base_seconds: float = Field(default=1.0)
    sync_backoff_max_seconds: float = Field(default=120.0)

    # --- Rate limiting ---------------------------------------------------
    rate_limit_default_per_minute: int = Field(default=120)

    # --- Security --------------------------------------------------------
    webhook_signature_tolerance_seconds: int = Field(default=300)
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @field_validator("egress_allowed_hosts", "egress_blocked_hosts", "cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
