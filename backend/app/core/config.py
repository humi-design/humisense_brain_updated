"""Application configuration.

All settings are read from environment variables (optionally via a ``.env``
file).  Nothing here contains production secrets - the credential-encryption
key is mandatory in production and validated at startup.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core.errors import ConfigurationError

# Environments in which header-based identity is permitted.  Anything else is
# treated as a real deployment and must authenticate with a verified token.
_NON_PRODUCTION_ENVIRONMENTS = {"development", "dev", "local", "test", "testing"}

# Algorithms that require a shared secret rather than a public key.
_SYMMETRIC_ALGORITHMS = {"HS256", "HS384", "HS512"}


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
    egress_allowed_hosts: Annotated[list[str], NoDecode] = Field(default_factory=list)
    egress_blocked_hosts: Annotated[list[str], NoDecode] = Field(default_factory=list)
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

    # --- Authentication --------------------------------------------------
    # ``oidc`` verifies a bearer JWT against a trusted provider.  ``header``
    # trusts X-Tenant-Id / X-User-Id headers and is REFUSED outside development
    # and test environments (see ``_validate_auth_configuration``).
    auth_mode: str = Field(default="header")
    auth_oidc_issuer: str | None = Field(default=None)
    auth_oidc_audience: str | None = Field(default=None)
    auth_oidc_jwks_url: str | None = Field(default=None)
    auth_oidc_algorithms: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["RS256", "ES256"]
    )
    # Symmetric secret, only for algorithms in ``_SYMMETRIC_ALGORITHMS``.
    auth_oidc_hmac_secret: str | None = Field(default=None)
    # Provider claim carrying tenant/org membership, e.g. "organization_id".
    auth_oidc_tenant_claim: str | None = Field(default=None)
    # When true, a token may select among memberships with ``X-Tenant-Id``.
    # It can only *select*, never grant.
    auth_allow_tenant_header_selection: bool = Field(default=True)
    auth_jwks_cache_seconds: int = Field(default=300)
    auth_leeway_seconds: int = Field(default=30)
    # Break-glass bootstrap: allows the first tenant + owner to be created with
    # no principal.  Must be false in production.
    bootstrap_token: str | None = Field(default=None)
    # Bearer token guarding ``/metrics``.  Required in production so that
    # operational counters are not world-readable.
    metrics_token: str | None = Field(default=None)

    # --- Security --------------------------------------------------------
    webhook_signature_tolerance_seconds: int = Field(default=300)
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    @field_validator(
        "egress_allowed_hosts",
        "egress_blocked_hosts",
        "cors_origins",
        "auth_oidc_algorithms",
        mode="before",
    )
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Accept both ``a,b`` and ``["a", "b"]``.

        The fields are annotated ``NoDecode``, so the raw environment string
        arrives here.  JSON form is still honoured because it was the only form
        pydantic-settings accepted before; existing deployments may use it.
        """
        if not isinstance(value, str):
            return value
        text = value.strip()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except ValueError:
                return value
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
            return value
        return [item.strip() for item in text.split(",") if item.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def allows_header_identity(self) -> bool:
        """True when header identity is actually usable.

        Requires both the header mode *and* a non-production environment.
        """
        return (
            self.auth_mode_normalised == "header"
            and self.environment.lower() in _NON_PRODUCTION_ENVIRONMENTS
        )

    @property
    def auth_mode_normalised(self) -> str:
        return (self.auth_mode or "").strip().lower()

    @model_validator(mode="after")
    def _validate_auth_configuration(self) -> Settings:
        """Fail closed: refuse to start with an unusable auth configuration.

        A misconfigured deployment must not fall back to trusting headers.
        """
        mode = self.auth_mode_normalised
        if mode not in {"oidc", "header"}:
            raise ConfigurationError(
                "HUMISENSE_AUTH_MODE must be 'oidc' or 'header' "
                f"(got {self.auth_mode!r})."
            )

        if mode == "header":
            if not self.allows_header_identity:
                raise ConfigurationError(
                    "HUMISENSE_AUTH_MODE=header trusts client-supplied identity "
                    "headers and is refused outside development/test. Set "
                    "HUMISENSE_AUTH_MODE=oidc and configure HUMISENSE_AUTH_OIDC_*."
                )
            return self

        # --- oidc ---------------------------------------------------------
        missing = [
            name
            for name, value in (
                ("HUMISENSE_AUTH_OIDC_ISSUER", self.auth_oidc_issuer),
                ("HUMISENSE_AUTH_OIDC_AUDIENCE", self.auth_oidc_audience),
            )
            if not value
        ]
        if not self.auth_oidc_jwks_url and not self.auth_oidc_hmac_secret:
            missing.append(
                "HUMISENSE_AUTH_OIDC_JWKS_URL (or HUMISENSE_AUTH_OIDC_HMAC_SECRET)"
            )
        if missing:
            raise ConfigurationError(
                "HUMISENSE_AUTH_MODE=oidc requires: " + ", ".join(missing)
            )

        algorithms = {a.strip().upper() for a in self.auth_oidc_algorithms}
        if not algorithms:
            raise ConfigurationError(
                "HUMISENSE_AUTH_OIDC_ALGORITHMS must list at least one algorithm."
            )
        # 'none' is never a valid choice, and symmetric algorithms would let a
        # leaked HMAC secret forge tokens for any issuer we trust.
        if "NONE" in algorithms:
            raise ConfigurationError("'none' is not a permitted signing algorithm.")
        if self.auth_oidc_jwks_url and algorithms & _SYMMETRIC_ALGORITHMS:
            raise ConfigurationError(
                "Symmetric algorithms (HS*) cannot be combined with a JWKS URL; "
                "they would trust a shared secret as a signing key."
            )
        if self.auth_oidc_hmac_secret and not algorithms & _SYMMETRIC_ALGORITHMS:
            raise ConfigurationError(
                "HUMISENSE_AUTH_OIDC_HMAC_SECRET is set but no HS* algorithm is enabled."
            )
        if not self.auth_oidc_jwks_url and not self.auth_oidc_hmac_secret:
            raise ConfigurationError(
                "A trusted key source (JWKS URL or HMAC secret) is required."
            )
        if self.bootstrap_token and self.is_production:
            raise ConfigurationError(
                "HUMISENSE_BOOTSTRAP_TOKEN must not be set in production."
            )
        if self.is_production and not self.metrics_token:
            raise ConfigurationError(
                "HUMISENSE_METRICS_TOKEN is required in production so that "
                "/metrics is not world-readable."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
