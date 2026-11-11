"""Authentication configuration tests.

These prove the fail-closed property: the application refuses to start with an
unusable or unsafe authentication configuration, and there is no development
bypass that can operate in production.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.errors import ConfigurationError

BASE = {
    "environment": "development",
    "credential_encryption_key": "0" * 64,
}


def _settings(**overrides) -> Settings:
    values = dict(BASE)
    values.update(overrides)
    return Settings(**values)


# ---------------------------------------------------------------------------
# Header mode is confined to development
# ---------------------------------------------------------------------------


def test_header_mode_allowed_in_development():
    settings = _settings(environment="development", auth_mode="header")
    assert settings.allows_header_identity is True


def test_header_mode_allowed_in_test():
    settings = _settings(environment="test", auth_mode="header")
    assert settings.allows_header_identity is True


def test_header_mode_refused_in_production():
    with pytest.raises(ConfigurationError) as exc:
        _settings(environment="production", auth_mode="header")
    assert "header" in str(exc.value)


def test_header_mode_refused_in_staging():
    """Any environment that is not explicitly development/test is treated strictly."""
    with pytest.raises(ConfigurationError):
        _settings(environment="staging", auth_mode="header")


def test_header_mode_is_the_default():
    assert _settings().auth_mode == "header"


def test_unknown_auth_mode_is_refused():
    with pytest.raises(ConfigurationError):
        _settings(auth_mode="trust-me")


# ---------------------------------------------------------------------------
# OIDC mode requires a complete, safe configuration
# ---------------------------------------------------------------------------


def test_oidc_requires_issuer():
    with pytest.raises(ConfigurationError) as exc:
        _settings(
            auth_mode="oidc",
            auth_oidc_audience="api",
            auth_oidc_jwks_url="https://idp.test/jwks",
        )
    assert "ISSUER" in str(exc.value)


def test_oidc_requires_audience():
    with pytest.raises(ConfigurationError) as exc:
        _settings(
            auth_mode="oidc",
            auth_oidc_issuer="https://idp.test/",
            auth_oidc_jwks_url="https://idp.test/jwks",
        )
    assert "AUDIENCE" in str(exc.value)


def test_oidc_requires_a_trusted_key_source():
    with pytest.raises(ConfigurationError) as exc:
        _settings(
            auth_mode="oidc",
            auth_oidc_issuer="https://idp.test/",
            auth_oidc_audience="api",
        )
    assert "JWKS" in str(exc.value)


def test_oidc_valid_configuration_is_accepted():
    settings = _settings(
        auth_mode="oidc",
        auth_oidc_issuer="https://idp.test/",
        auth_oidc_audience="api",
        auth_oidc_jwks_url="https://idp.test/jwks",
    )
    assert settings.auth_mode_normalised == "oidc"
    assert settings.allows_header_identity is False


def test_oidc_refuses_alg_none():
    with pytest.raises(ConfigurationError) as exc:
        _settings(
            auth_mode="oidc",
            auth_oidc_issuer="https://idp.test/",
            auth_oidc_audience="api",
            auth_oidc_jwks_url="https://idp.test/jwks",
            auth_oidc_algorithms=["none"],
        )
    assert "none" in str(exc.value).lower()


def test_oidc_refuses_symmetric_algorithm_with_jwks():
    """HS256 plus a JWKS URL would let a shared secret sign for any issuer."""
    with pytest.raises(ConfigurationError) as exc:
        _settings(
            auth_mode="oidc",
            auth_oidc_issuer="https://idp.test/",
            auth_oidc_audience="api",
            auth_oidc_jwks_url="https://idp.test/jwks",
            auth_oidc_algorithms=["RS256", "HS256"],
        )
    assert "Symmetric" in str(exc.value) or "symmetric" in str(exc.value)


def test_oidc_hmac_secret_requires_symmetric_algorithm():
    with pytest.raises(ConfigurationError):
        _settings(
            auth_mode="oidc",
            auth_oidc_issuer="https://idp.test/",
            auth_oidc_audience="api",
            auth_oidc_hmac_secret="s" * 32,
            auth_oidc_algorithms=["RS256"],
        )


def test_oidc_hmac_only_configuration_is_accepted():
    settings = _settings(
        auth_mode="oidc",
        auth_oidc_issuer="https://idp.test/",
        auth_oidc_audience="api",
        auth_oidc_hmac_secret="s" * 32,
        auth_oidc_algorithms=["HS256"],
    )
    assert settings.auth_mode_normalised == "oidc"


def test_oidc_refuses_empty_algorithm_list():
    with pytest.raises(ConfigurationError):
        _settings(
            auth_mode="oidc",
            auth_oidc_issuer="https://idp.test/",
            auth_oidc_audience="api",
            auth_oidc_jwks_url="https://idp.test/jwks",
            auth_oidc_algorithms=[],
        )


# ---------------------------------------------------------------------------
# Bootstrap token is a development-only affordance
# ---------------------------------------------------------------------------


def test_bootstrap_token_refused_in_production():
    with pytest.raises(ConfigurationError) as exc:
        _settings(
            environment="production",
            auth_mode="oidc",
            auth_oidc_issuer="https://idp.test/",
            auth_oidc_audience="api",
            auth_oidc_jwks_url="https://idp.test/jwks",
            bootstrap_token="would-be-backdoor",
        )
    assert "BOOTSTRAP_TOKEN" in str(exc.value)


def test_bootstrap_token_allowed_in_development():
    settings = _settings(bootstrap_token="dev-only")
    assert settings.bootstrap_token == "dev-only"


# ---------------------------------------------------------------------------
# Algorithm parsing
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# CSV environment parsing
# ---------------------------------------------------------------------------
# Regression: pydantic-settings JSON-decodes list fields before validators run,
# so ``HUMISENSE_CORS_ORIGINS=a,b`` used to crash startup with a SettingsError.
# The fields are annotated ``NoDecode`` so the CSV validator sees the raw string.


@pytest.mark.parametrize(
    ("env_var", "value", "attribute", "expected"),
    [
        ("HUMISENSE_CORS_ORIGINS", "http://a.test,http://b.test", "cors_origins", ["http://a.test", "http://b.test"]),
        ("HUMISENSE_EGRESS_ALLOWED_HOSTS", "api.test,x.test", "egress_allowed_hosts", ["api.test", "x.test"]),
        ("HUMISENSE_EGRESS_BLOCKED_HOSTS", "bad.test", "egress_blocked_hosts", ["bad.test"]),
        ("HUMISENSE_AUTH_OIDC_ALGORITHMS", "RS256", "auth_oidc_algorithms", ["RS256"]),
    ],
)
def test_csv_env_lists_parse(monkeypatch, env_var, value, attribute, expected):
    monkeypatch.setenv(env_var, value)
    settings = Settings(environment="development", credential_encryption_key="0" * 64)
    assert getattr(settings, attribute) == expected


def test_csv_env_list_accepts_json_form(monkeypatch):
    """A JSON array must keep working, for callers already using that form."""
    monkeypatch.setenv("HUMISENSE_CORS_ORIGINS", '["http://a.test"]')
    settings = Settings(environment="development", credential_encryption_key="0" * 64)
    assert settings.cors_origins == ["http://a.test"]


def test_algorithms_accept_comma_separated_string():
    settings = _settings(
        auth_mode="oidc",
        auth_oidc_issuer="https://idp.test/",
        auth_oidc_audience="api",
        auth_oidc_jwks_url="https://idp.test/jwks",
        auth_oidc_algorithms="RS256,ES256",
    )
    assert settings.auth_oidc_algorithms == ["RS256", "ES256"]


# ---------------------------------------------------------------------------
# Metrics endpoint exposure
# ---------------------------------------------------------------------------


def test_metrics_requires_token_when_configured(db):
    from fastapi.testclient import TestClient

    from app.core.config import settings as live
    from app.main import app

    original = live.metrics_token
    live.metrics_token = "metrics-secret"
    try:
        with TestClient(app) as client:
            anon = client.get("/api/v1/metrics")
            wrong = client.get(
                "/api/v1/metrics", headers={"Authorization": "Bearer nope"}
            )
            right = client.get(
                "/api/v1/metrics", headers={"Authorization": "Bearer metrics-secret"}
            )
    finally:
        live.metrics_token = original

    assert anon.status_code == 401
    assert wrong.status_code == 401
    assert right.status_code == 200
    assert "humisense_layer1_up 1" in right.text


def test_metrics_token_required_in_production():
    with pytest.raises(ConfigurationError) as exc:
        _settings(
            environment="production",
            auth_mode="oidc",
            auth_oidc_issuer="https://idp.test/",
            auth_oidc_audience="api",
            auth_oidc_jwks_url="https://idp.test/jwks",
            metrics_token=None,
        )
    assert "METRICS_TOKEN" in str(exc.value)
