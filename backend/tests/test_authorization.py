"""Authorization tests.

The central claim under test: in ``oidc`` mode a client cannot influence its own
tenant or role.  ``X-Tenant-Id`` and ``X-User-Role`` are either ignored or used
only to *select* among memberships the verified subject already holds.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings as app_settings
from app.db import models
from tests import authkit
from tests.authkit import ISSUER, JwksServer, SigningKey


@pytest.fixture(scope="module")
def signing_key() -> SigningKey:
    return SigningKey()


@pytest.fixture(scope="module")
def jwks(signing_key):
    server = JwksServer([signing_key]).start()
    yield server
    server.stop()


@pytest.fixture
def oidc(jwks):
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
    settings.auth_oidc_audience = authkit.AUDIENCE
    settings.auth_oidc_jwks_url = jwks.url
    settings.auth_oidc_algorithms = ["RS256"]
    from app.api import deps

    deps.reset_verifier_cache()
    yield settings
    for key, value in original.items():
        setattr(settings, key, value)
    deps.reset_verifier_cache()


def _member(db, tenant, subject, role, email=None):
    row = models.User(
        id=str(uuid.uuid4()),
        tenant_id=tenant.id,
        email=email or f"{subject}@example.test",
        display_name=subject,
        role=role,
        is_active=True,
        external_issuer=ISSUER,
        external_subject=subject,
    )
    db.add(row)
    db.commit()
    return row


def _auth(subject: str, key: SigningKey, **headers) -> dict:
    token = key.sign(authkit.claims(sub=subject))
    return {"Authorization": f"Bearer {token}", **headers}


# ---------------------------------------------------------------------------
# Header manipulation cannot change identity or role
# ---------------------------------------------------------------------------


def test_user_role_header_cannot_escalate(oidc, db, tenant, signing_key):
    """A viewer setting X-User-Role: admin is still a viewer."""
    from app.main import app

    _member(db, tenant, "viewer-1", "viewer")
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/whoami",
            headers=_auth("viewer-1", signing_key, **{"X-User-Role": "admin"}),
        )
    assert response.status_code == 200
    assert response.json()["role"] == "viewer"
    assert response.json()["is_admin"] is False


def test_user_role_header_cannot_authorize_admin_action(oidc, db, tenant, signing_key):
    """The same escalation attempt on a real admin-only endpoint is refused."""
    from app.main import app

    _member(db, tenant, "viewer-1", "viewer")
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/connections",
            headers=_auth("viewer-1", signing_key, **{"X-User-Role": "owner"}),
            json={"connector_id": "github", "display_name": "X", "credentials": {"token": "t"}},
        )
    assert response.status_code == 403


def test_tenant_id_header_cannot_impersonate_another_tenant(oidc, db, tenant, other_tenant, signing_key):
    """A member of tenant A asking for tenant B is refused, not granted."""
    from app.main import app

    _member(db, tenant, "user-a", "owner")
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/connections",
            headers=_auth("user-a", signing_key, **{"X-Tenant-Id": other_tenant.id}),
        )
    assert response.status_code == 403


def test_tenant_id_header_selects_among_own_memberships(oidc, db, tenant, other_tenant, signing_key):
    """A subject genuinely in two tenants may select which one to act in."""
    from app.main import app

    _member(db, tenant, "multi", "owner", email="multi@example.test")
    _member(db, other_tenant, "multi", "viewer", email="multi2@example.test")
    with TestClient(app) as client:
        first = client.get(
            "/api/v1/tenants/whoami",
            headers=_auth("multi", signing_key, **{"X-Tenant-Id": tenant.id}),
        )
        second = client.get(
            "/api/v1/tenants/whoami",
            headers=_auth("multi", signing_key, **{"X-Tenant-Id": other_tenant.id}),
        )
    assert first.json()["tenant_id"] == tenant.id
    assert first.json()["role"] == "owner"
    assert second.json()["tenant_id"] == other_tenant.id
    assert second.json()["role"] == "viewer"


def test_multi_tenant_subject_without_selection_is_ambiguous(oidc, db, tenant, other_tenant, signing_key):
    from app.main import app

    _member(db, tenant, "multi", "owner", email="m1@example.test")
    _member(db, other_tenant, "multi", "member", email="m2@example.test")
    with TestClient(app) as client:
        response = client.get("/api/v1/tenants/whoami", headers=_auth("multi", signing_key))
    assert response.status_code == 403


def test_unknown_tenant_header_is_403_not_404(oidc, db, tenant, signing_key):
    """Refusal must not leak whether the tenant exists."""
    from app.main import app

    _member(db, tenant, "user-a", "owner")
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/connections",
            headers=_auth("user-a", signing_key, **{"X-Tenant-Id": "no-such-tenant"}),
        )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Cross-tenant resource access
# ---------------------------------------------------------------------------


def test_cross_tenant_resource_read_is_404(oidc, db, tenant, other_tenant, signing_key):
    from app.main import app
    from app.schemas.contracts import ConnectionConfiguration
    from app.services.connection_service import ConnectionService

    _member(db, tenant, "user-a", "owner")
    _member(db, other_tenant, "user-b", "owner")
    connection = ConnectionService(db).create_connection(
        tenant.id,
        connector_id="github",
        display_name="A conn",
        configuration=ConnectionConfiguration(base_url="https://api.github.com"),
        credentials={"token": "t"},
        actor_id="user-a",
    )
    db.commit()

    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/connections/{connection.id}",
            headers=_auth("user-b", signing_key, **{"X-Tenant-Id": other_tenant.id}),
        )
    assert response.status_code == 404


def test_cross_tenant_delete_is_404_and_leaves_row(oidc, db, tenant, other_tenant, signing_key):
    from app.main import app
    from app.schemas.contracts import ConnectionConfiguration
    from app.services.connection_service import ConnectionService

    _member(db, tenant, "user-a", "owner")
    _member(db, other_tenant, "user-b", "owner")
    connection = ConnectionService(db).create_connection(
        tenant.id,
        connector_id="github",
        display_name="A conn",
        configuration=ConnectionConfiguration(base_url="https://api.github.com"),
        credentials={"token": "t"},
        actor_id="user-a",
    )
    db.commit()

    with TestClient(app) as client:
        response = client.delete(
            f"/api/v1/connections/{connection.id}",
            headers=_auth("user-b", signing_key, **{"X-Tenant-Id": other_tenant.id}),
        )
    assert response.status_code == 404

    db.expire_all()
    still_there = db.get(models.Connection, connection.id)
    assert still_there is not None
    assert still_there.status != "revoked"


def test_cross_tenant_revoke_is_404(oidc, db, tenant, other_tenant, signing_key):
    from app.main import app
    from app.schemas.contracts import ConnectionConfiguration
    from app.services.connection_service import ConnectionService

    _member(db, tenant, "user-a", "owner")
    _member(db, other_tenant, "user-b", "owner")
    connection = ConnectionService(db).create_connection(
        tenant.id,
        connector_id="github",
        display_name="A conn",
        configuration=ConnectionConfiguration(base_url="https://api.github.com"),
        credentials={"token": "t"},
        actor_id="user-a",
    )
    db.commit()

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/connections/{connection.id}/revoke",
            headers=_auth("user-b", signing_key, **{"X-Tenant-Id": other_tenant.id}),
        )
    assert response.status_code == 404


def test_list_connections_is_scoped_to_principal(oidc, db, tenant, other_tenant, signing_key):
    from app.main import app
    from app.schemas.contracts import ConnectionConfiguration
    from app.services.connection_service import ConnectionService

    _member(db, tenant, "user-a", "owner")
    _member(db, other_tenant, "user-b", "owner")
    service = ConnectionService(db)
    service.create_connection(
        tenant.id,
        connector_id="github",
        display_name="A only",
        configuration=ConnectionConfiguration(base_url="https://api.github.com"),
        credentials={"token": "t"},
        actor_id="user-a",
    )
    db.commit()

    with TestClient(app) as client:
        a = client.get(
            "/api/v1/connections",
            headers=_auth("user-a", signing_key, **{"X-Tenant-Id": tenant.id}),
        )
        b = client.get(
            "/api/v1/connections",
            headers=_auth("user-b", signing_key, **{"X-Tenant-Id": other_tenant.id}),
        )
    assert len(a.json()) == 1
    assert b.json() == []


# ---------------------------------------------------------------------------
# Role enforcement on the principal itself
# ---------------------------------------------------------------------------


def test_member_role_cannot_create_connection(oidc, db, tenant, signing_key):
    from app.main import app

    _member(db, tenant, "member-1", "member")
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/connections",
            headers=_auth("member-1", signing_key, **{"X-Tenant-Id": tenant.id}),
            json={"connector_id": "github", "display_name": "X", "credentials": {"token": "t"}},
        )
    assert response.status_code == 403


def test_admin_role_can_create_connection(oidc, db, tenant, signing_key):
    from app.main import app

    _member(db, tenant, "admin-1", "admin")
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/connections",
            headers=_auth("admin-1", signing_key, **{"X-Tenant-Id": tenant.id}),
            json={"connector_id": "github", "display_name": "X", "credentials": {"token": "t"}},
        )
    assert response.status_code == 201
    assert response.json()["status"] == "configured"


def test_corrupt_role_is_refused(oidc, db, tenant, signing_key):
    """A role value outside the known set must not be treated as privileged."""
    from app.main import app

    _member(db, tenant, "weird", "superuser")
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/connections",
            headers=_auth("weird", signing_key, **{"X-Tenant-Id": tenant.id}),
        )
    assert response.status_code == 403


def test_membership_of_other_tenant_cannot_be_used_with_wrong_tenant_header(
    oidc, db, tenant, other_tenant, signing_key
):
    """Subject is only a member of A; asking for B while being an admin there is denied."""
    from app.main import app

    _member(db, tenant, "only-a", "owner")
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/connections",
            headers=_auth("only-a", signing_key, **{"X-Tenant-Id": other_tenant.id}),
            json={"connector_id": "github", "display_name": "X", "credentials": {"token": "t"}},
        )
    assert response.status_code == 403
