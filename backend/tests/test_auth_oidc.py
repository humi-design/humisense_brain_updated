"""Authentication tests: OIDC/JWT verification.

Every token here is genuinely signed with a real RSA key, and the JWKS is
served over real HTTP, so the production verification path runs end to end.
Nothing in this module mocks the security logic.

The header-trust mode is exercised separately in
``test_tenant_isolation.py`` (development) and ``test_auth_config.py``
(refusal outside development).
"""

from __future__ import annotations

import time
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings as app_settings
from app.core.identity import TokenVerifier
from app.db import models
from tests import authkit
from tests.authkit import AUDIENCE, ISSUER, JwksServer, SigningKey


@pytest.fixture(scope="module")
def signing_key() -> SigningKey:
    return SigningKey()


@pytest.fixture(scope="module")
def jwks(signing_key):
    server = JwksServer([signing_key]).start()
    yield server
    server.stop()


@pytest.fixture
def oidc_settings(jwks):
    """Switch the process into OIDC mode against the test JWKS.

    Uses the module-level ``settings`` object, which is the instance the
    application imports — not a fresh ``get_settings()`` result.
    """
    settings = app_settings
    original = {
        "auth_mode": settings.auth_mode,
        "auth_oidc_issuer": settings.auth_oidc_issuer,
        "auth_oidc_audience": settings.auth_oidc_audience,
        "auth_oidc_jwks_url": settings.auth_oidc_jwks_url,
        "auth_oidc_algorithms": list(settings.auth_oidc_algorithms),
    }
    settings.auth_mode = "oidc"
    settings.auth_oidc_issuer = ISSUER
    settings.auth_oidc_audience = AUDIENCE
    settings.auth_oidc_jwks_url = jwks.url
    settings.auth_oidc_algorithms = ["RS256"]

    from app.api import deps

    deps.reset_verifier_cache()
    yield settings
    for key, value in original.items():
        setattr(settings, key, value)
    deps.reset_verifier_cache()


@pytest.fixture
def verifier(oidc_settings) -> TokenVerifier:
    return TokenVerifier(oidc_settings)


def _membership(db, tenant, subject="user-1", role="owner", *, issuer=ISSUER, active=True):
    row = models.User(
        id=str(uuid.uuid4()),
        tenant_id=tenant.id,
        email=f"{subject}@example.test",
        display_name=subject,
        role=role,
        is_active=active,
        external_issuer=issuer,
        external_subject=subject,
    )
    db.add(row)
    db.commit()
    return row


# ---------------------------------------------------------------------------
# Token verification — the library boundary
# ---------------------------------------------------------------------------


def test_valid_token_verifies(verifier, signing_key):
    claims = verifier.verify(signing_key.sign(authkit.claims()))
    assert claims.subject == "user-1"
    assert claims.issuer == ISSUER


def test_invalid_signature_is_rejected(verifier, signing_key):
    """Signed by a rogue key whose kid claims to be the trusted one."""
    from app.core.identity import TokenVerificationError

    token = authkit.wrong_key_token(signing_key)
    with pytest.raises(TokenVerificationError) as exc:
        verifier.verify(token)
    assert exc.value.reason == "bad_signature"


def test_wrong_issuer_is_rejected(verifier, signing_key):
    from app.core.identity import TokenVerificationError

    token = signing_key.sign(authkit.claims(iss="https://evil.test/"))
    with pytest.raises(TokenVerificationError) as exc:
        verifier.verify(token)
    assert exc.value.reason == "bad_issuer"


def test_wrong_audience_is_rejected(verifier, signing_key):
    from app.core.identity import TokenVerificationError

    token = signing_key.sign(authkit.claims(aud="some-other-api"))
    with pytest.raises(TokenVerificationError) as exc:
        verifier.verify(token)
    assert exc.value.reason == "bad_audience"


def test_expired_token_is_rejected(verifier, signing_key):
    from app.core.identity import TokenVerificationError

    now = int(time.time())
    token = signing_key.sign(authkit.claims(exp=now - 3600, iat=now - 7200, nbf=now - 7200))
    with pytest.raises(TokenVerificationError) as exc:
        verifier.verify(token)
    assert exc.value.reason == "expired"


def test_not_yet_valid_token_is_rejected(verifier, signing_key):
    from app.core.identity import TokenVerificationError

    now = int(time.time())
    token = signing_key.sign(authkit.claims(nbf=now + 3600, exp=now + 7200))
    with pytest.raises(TokenVerificationError) as exc:
        verifier.verify(token)
    assert exc.value.reason == "not_yet_valid"


def test_missing_subject_is_rejected(verifier, signing_key):
    from app.core.identity import TokenVerificationError

    token = signing_key.sign(authkit.claims(sub=""))
    with pytest.raises(TokenVerificationError):
        verifier.verify(token)


def test_malformed_token_is_rejected(verifier):
    from app.core.identity import TokenVerificationError

    with pytest.raises(TokenVerificationError):
        verifier.verify("not-a-jwt")


def test_empty_token_is_rejected(verifier):
    from app.core.identity import TokenVerificationError

    with pytest.raises(TokenVerificationError):
        verifier.verify("   ")


def test_unsigned_token_is_rejected(verifier, signing_key):
    """alg=none must never be accepted."""
    from app.core.identity import TokenVerificationError

    unsigned = jwt.encode(authkit.claims(), key="", algorithm="none")
    with pytest.raises(TokenVerificationError):
        verifier.verify(unsigned)


def test_token_signed_with_untrusted_algorithm_is_rejected(verifier, signing_key):
    """An HS256 token cannot be verified against an RSA JWKS."""
    from app.core.identity import TokenVerificationError

    hs = jwt.encode(authkit.claims(), "shared-secret", algorithm="HS256")
    with pytest.raises(TokenVerificationError):
        verifier.verify(hs)


def test_unknown_kid_is_rejected(verifier, signing_key):
    from app.core.identity import TokenVerificationError

    token = signing_key.sign(authkit.claims(), kid="key-that-does-not-exist")
    with pytest.raises(TokenVerificationError):
        verifier.verify(token)


# ---------------------------------------------------------------------------
# End-to-end HTTP authentication
# ---------------------------------------------------------------------------


def test_request_without_token_is_401(oidc_settings, db, tenant):
    from app.main import app

    with TestClient(app) as client:
        response = client.get("/api/v1/connections")
    assert response.status_code == 401


def test_request_with_malformed_bearer_is_401(oidc_settings, db, tenant):
    from app.main import app

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/connections", headers={"Authorization": "Basic abc"}
        )
    assert response.status_code == 401


def test_valid_token_authenticates(oidc_settings, db, tenant, signing_key):
    from app.main import app

    _membership(db, tenant, "user-1")
    token = signing_key.sign(authkit.claims(sub="user-1"))
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/whoami", headers={"Authorization": f"Bearer {token}"}
        )
    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == tenant.id
    assert body["role"] == "owner"
    assert body["subject"] == "user-1"
    assert body["source"] == "oidc"


def test_unknown_subject_is_403(oidc_settings, db, tenant, signing_key):
    """A valid token for a subject with no membership is authorised nowhere."""
    from app.main import app

    token = signing_key.sign(authkit.claims(sub="nobody"))
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/connections", headers={"Authorization": f"Bearer {token}"}
        )
    assert response.status_code == 403


def test_disabled_membership_is_403(oidc_settings, db, tenant, signing_key):
    from app.main import app

    _membership(db, tenant, "user-1", active=False)
    token = signing_key.sign(authkit.claims(sub="user-1"))
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/connections", headers={"Authorization": f"Bearer {token}"}
        )
    assert response.status_code == 403


def test_membership_in_inactive_tenant_is_403(oidc_settings, db, tenant, signing_key):
    from app.main import app

    _membership(db, tenant, "user-1")
    tenant.is_active = False
    db.commit()
    token = signing_key.sign(authkit.claims(sub="user-1"))
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/connections", headers={"Authorization": f"Bearer {token}"}
        )
    assert response.status_code == 403


def test_invalid_token_on_real_endpoint_is_401(oidc_settings, db, tenant, signing_key):
    from app.main import app

    _membership(db, tenant, "user-1")
    token = authkit.wrong_key_token(signing_key, sub="user-1")
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/connections", headers={"Authorization": f"Bearer {token}"}
        )
    assert response.status_code == 401
