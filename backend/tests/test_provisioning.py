"""Tenant provisioning tests.

Covers the audit's critical defect: a clean database must be able to create a
tenant, its first owner, and then a connection — the exact sequence that
previously failed with a foreign-key error.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings as app_settings
from app.core.errors import (
    AuthorizationError,
    ConflictError,
    ValidationError,
)
from app.db import models
from app.services.tenant_service import TenantService, slugify

BOOTSTRAP_TOKEN = "test-bootstrap-token-value"


def _persist_registry(db) -> None:
    """Populate connector_registrations so connection FKs resolve."""
    from app.connectors.bootstrap import persist_registry

    persist_registry(db)
    db.commit()


@pytest.fixture
def bootstrap_token():
    original = app_settings.bootstrap_token
    app_settings.bootstrap_token = BOOTSTRAP_TOKEN
    yield BOOTSTRAP_TOKEN
    app_settings.bootstrap_token = original


# ---------------------------------------------------------------------------
# Service level
# ---------------------------------------------------------------------------


def test_slugify():
    assert slugify("Acme Manufacturing Ltd") == "acme-manufacturing-ltd"
    assert slugify("  Weird -- Name!!  ") == "weird-name"
    assert slugify("Ünïcode & Co") == "n-code-co"


def test_create_tenant_creates_owner_atomically(db):
    service = TenantService(db)
    result = service.create_tenant(
        name="Acme Manufacturing",
        owner_email="Owner@Example.test",
        actor_id=None,
    )
    db.commit()

    assert result.tenant.slug == "acme-manufacturing"
    assert result.owner.role == "owner"
    assert result.owner.email == "owner@example.test"  # normalised
    assert result.owner.tenant_id == result.tenant.id

    # The tenant is readable and the membership is linked.
    assert db.get(models.Tenant, result.tenant.id) is not None
    membership = db.get(models.User, result.owner.id)
    assert membership.tenant_id == result.tenant.id


def test_create_tenant_rejects_duplicate_slug(db):
    service = TenantService(db)
    service.create_tenant(name="Acme", owner_email="a@example.test")
    db.commit()
    with pytest.raises(ConflictError):
        service.create_tenant(name="Acme", owner_email="b@example.test")


def test_create_tenant_rejects_invalid_input(db):
    service = TenantService(db)
    with pytest.raises(ValidationError):
        service.create_tenant(name="   ", owner_email="a@example.test")
    with pytest.raises(ValidationError):
        service.create_tenant(name="Acme", owner_email="not-an-email")
    with pytest.raises(ValidationError):
        service.create_tenant(name="Acme", slug="Bad Slug!", owner_email="a@example.test")


def test_connection_can_be_created_after_provisioning(db):
    """The audit's failing sequence, now working on a clean database."""
    from app.schemas.contracts import ConnectionConfiguration
    from app.services.connection_service import ConnectionService

    _persist_registry(db)
    service = TenantService(db)
    result = service.create_tenant(name="Fresh Corp", owner_email="o@example.test")
    db.commit()

    connection = ConnectionService(db).create_connection(
        result.tenant.id,
        connector_id="github",
        display_name="First connection",
        configuration=ConnectionConfiguration(base_url="https://api.github.com"),
        credentials={"token": "ghp_x"},
        actor_id=result.owner.id,
    )
    db.commit()
    assert connection.id
    assert connection.tenant_id == result.tenant.id


def test_duplicate_membership_is_rejected(db):
    service = TenantService(db)
    result = service.create_tenant(name="Acme", owner_email="owner@example.test")
    db.commit()
    with pytest.raises(ConflictError):
        service.add_membership(result.tenant.id, email="owner@example.test", role="member")


def test_add_membership_validates_role(db):
    service = TenantService(db)
    result = service.create_tenant(name="Acme", owner_email="owner@example.test")
    db.commit()
    with pytest.raises(ValidationError):
        service.add_membership(result.tenant.id, email="x@example.test", role="superuser")


def test_cannot_revoke_last_owner(db):
    service = TenantService(db)
    result = service.create_tenant(name="Acme", owner_email="owner@example.test")
    db.commit()
    with pytest.raises(ConflictError):
        service.set_membership_active(result.tenant.id, result.owner.id, active=False)


def test_can_revoke_owner_when_another_exists(db):
    service = TenantService(db)
    result = service.create_tenant(name="Acme", owner_email="owner@example.test")
    second = service.add_membership(result.tenant.id, email="second@example.test", role="owner")
    db.commit()
    service.set_membership_active(result.tenant.id, result.owner.id, active=False)
    db.commit()
    assert db.get(models.User, result.owner.id).is_active is False
    assert db.get(models.User, second.id).is_active is True


def test_identity_linking_rejects_duplicate_subject(db):
    service = TenantService(db)
    result = service.create_tenant(name="Acme", owner_email="owner@example.test")
    service.add_membership(
        result.tenant.id, email="a@example.test", external_issuer="https://i/", external_subject="s1"
    )
    b = service.add_membership(result.tenant.id, email="b@example.test")
    db.commit()
    with pytest.raises(ConflictError):
        service.link_identity(result.tenant.id, b.id, issuer="https://i/", subject="s1")


def test_provisioning_is_audited(db):
    service = TenantService(db)
    result = service.create_tenant(name="Acme", owner_email="owner@example.test", actor_id="admin-1")
    db.commit()
    actions = {
        row.action
        for row in db.query(models.AuditLog)
        .filter(models.AuditLog.tenant_id == result.tenant.id)
        .all()
    }
    assert "tenant_created" in actions
    assert "membership_created" in actions


def test_failed_provisioning_rolls_back(db):
    """A duplicate slug must leave no partial tenant or membership."""
    service = TenantService(db)
    service.create_tenant(name="Acme", owner_email="a@example.test")
    db.commit()
    before = db.query(models.Tenant).count()

    with pytest.raises(ConflictError):
        service.create_tenant(name="Acme", owner_email="b@example.test")
    db.rollback()
    assert db.query(models.Tenant).count() == before


def test_bootstrap_requires_configured_token(db):
    service = TenantService(db)
    original = app_settings.bootstrap_token
    app_settings.bootstrap_token = None
    try:
        with pytest.raises(AuthorizationError):
            service.assert_bootstrap_authorised("anything", None)
    finally:
        app_settings.bootstrap_token = original


def test_bootstrap_rejects_wrong_token(db):
    from app.core.errors import AuthenticationError

    service = TenantService(db)
    with pytest.raises(AuthenticationError):
        service.assert_bootstrap_authorised("wrong", "right")


# ---------------------------------------------------------------------------
# HTTP level
# ---------------------------------------------------------------------------


def test_bootstrap_status_reports_need(db):
    from app.main import app

    with TestClient(app) as client:
        response = client.get("/api/v1/tenants/bootstrap-status")
    assert response.status_code == 200
    assert response.json()["bootstrap_required"] is True


def test_bootstrap_creates_first_tenant(db, bootstrap_token):
    from app.main import app

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tenants",
            headers={"X-Bootstrap-Token": bootstrap_token},
            json={"name": "First Corp", "owner_email": "founder@example.test"},
        )
    assert response.status_code == 201
    body = response.json()
    assert body["slug"] == "first-corp"
    assert body["is_active"] is True


def test_bootstrap_without_token_is_refused(db, bootstrap_token):
    from app.main import app

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tenants",
            json={"name": "Sneaky Corp", "owner_email": "sneak@example.test"},
        )
    assert response.status_code == 401
    assert db.query(models.Tenant).count() == 0


def test_bootstrap_with_wrong_token_is_refused(db, bootstrap_token):
    from app.main import app

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tenants",
            headers={"X-Bootstrap-Token": "not-the-token"},
            json={"name": "Sneaky Corp", "owner_email": "sneak@example.test"},
        )
    assert response.status_code == 401
    assert db.query(models.Tenant).count() == 0


def test_bootstrap_closes_once_a_tenant_exists(db, tenant, bootstrap_token):
    """Even with the correct token, the bootstrap path is closed afterwards."""
    from app.main import app

    _persist_registry(db)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tenants",
            headers={"X-Bootstrap-Token": bootstrap_token},
            json={"name": "Second Corp", "owner_email": "second@example.test"},
        )
    # A tenant already exists, so this must go down the admin path and fail
    # for lack of an authenticated principal — never succeed on the token alone.
    assert response.status_code in {401, 403}


def test_anonymous_cannot_create_tenant_after_bootstrap(db, tenant):
    from app.main import app

    _persist_registry(db)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tenants",
            json={"name": "Anonymous Corp", "owner_email": "anon@example.test"},
        )
    assert response.status_code == 401
