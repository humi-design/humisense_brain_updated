"""End-to-end API tests via FastAPI TestClient.

These drive the real HTTP surface (auth, tenant headers, error mapping) and
prove the acceptance criteria that can be checked without a live provider:
register, authorise, test (mocked transport), resource selection, sync,
tenant isolation, revocation and discovery.

**Authentication note.** These tests run in ``header`` mode, which is the
development/test identity mode.  It is permitted only because
``HUMISENSE_ENVIRONMENT=test``; ``Settings`` refuses to start with header mode
in any other environment, and ``tests/test_auth_config.py`` proves that.  The
real token-verification path is covered by ``tests/test_auth_oidc.py`` and
``tests/test_authorization.py``.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import models
from app.main import app


@pytest.fixture
def client(db, tenant):
    from app.connectors.bootstrap import persist_registry

    persist_registry(db)
    db.commit()
    with TestClient(app) as test_client:
        test_client.headers.update(
            {"X-Tenant-Id": tenant.id, "X-User-Id": "u1", "X-User-Role": "admin"}
        )
        yield test_client


def test_health_endpoint(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["connectors_registered"] > 0
    assert body["connectors_installable"] > 0


def test_requires_tenant_header():
    with TestClient(app) as test_client:
        response = test_client.get("/api/v1/connectors")
        assert response.status_code == 401


def test_list_connectors_marks_installability(client):
    response = client.get("/api/v1/connectors")
    assert response.status_code == 200
    catalogue = {item["connector_id"]: item for item in response.json()}
    assert catalogue["github"]["is_installable"] is True
    assert catalogue["salesforce"]["is_installable"] is False
    assert catalogue["salesforce"]["implementation_state"] == "PLANNED"


def test_connector_search_and_category_filter(client):
    response = client.get("/api/v1/connectors", params={"search": "canary"})
    assert response.status_code == 200
    ids = [item["connector_id"] for item in response.json()]
    assert "canary_labs" in ids

    response = client.get("/api/v1/connectors", params={"category": "manufacturing_industrial"})
    assert response.status_code == 200
    assert all(item["category"] == "manufacturing_industrial" for item in response.json())


def test_create_connection_hides_credentials(client):
    response = client.post(
        "/api/v1/connections",
        json={
            "connector_id": "github",
            "display_name": "GitHub Prod",
            "configuration": {"base_url": "https://api.github.com", "options": {"api_base": "https://api.github.com"}},
            "credentials": {"token": "ghp_supersecret"},
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert "ghp_supersecret" not in response.text
    assert body["credential_reference_id"] is not None
    assert body["status"] == "configured"


def test_create_connection_requires_admin_role(db, tenant):
    from app.connectors.bootstrap import persist_registry

    persist_registry(db)
    db.commit()
    with TestClient(app) as test_client:
        test_client.headers.update(
            {"X-Tenant-Id": tenant.id, "X-User-Id": "u2", "X-User-Role": "viewer"}
        )
        response = test_client.post(
            "/api/v1/connections",
            json={"connector_id": "github", "display_name": "X", "credentials": {"token": "t"}},
        )
        assert response.status_code == 403


def test_connection_is_not_marked_connected_until_tested(client, db, monkeypatch):
    created = client.post(
        "/api/v1/connections",
        json={
            "connector_id": "github",
            "display_name": "GH",
            "configuration": {"base_url": "https://api.github.com", "options": {"api_base": "https://api.github.com"}},
            "credentials": {"token": "ghp_mock"},
        },
    ).json()
    assert created["status"] == "configured"

    # Inject a fake transport so no real network call is made.
    from app.connectors.providers import github_connector
    from tests.fake_http import FakeHttpClient, static

    fake = FakeHttpClient(
        {("GET", "/user"): static(200, {"login": "acme"}, {"x-oauth-scopes": "repo"})}
    )
    original = github_connector.GitHubConnector._http
    monkeypatch.setattr(
        github_connector.GitHubConnector, "_http", lambda self: fake
    )

    response = client.post(f"/api/v1/connections/{created['connection_id']}/test")
    assert response.status_code == 200
    assert response.json()["success"] is True

    refreshed = client.get(f"/api/v1/connections/{created['connection_id']}").json()
    assert refreshed["status"] == "connected"
    assert refreshed["health_status"] == "healthy"
    assert refreshed["account_identifier"] == "acme"


def test_failed_connection_test_is_recorded(client, monkeypatch):
    created = client.post(
        "/api/v1/connections",
        json={
            "connector_id": "github",
            "display_name": "GH bad",
            "configuration": {"base_url": "https://api.github.com", "options": {"api_base": "https://api.github.com"}},
            "credentials": {"token": "ghp_bad"},
        },
    ).json()

    from app.connectors.providers import github_connector
    from tests.fake_http import FakeHttpClient, static

    fake = FakeHttpClient({("GET", "/user"): static(401, {"message": "Bad credentials"})})
    monkeypatch.setattr(github_connector.GitHubConnector, "_http", lambda self: fake)

    response = client.post(f"/api/v1/connections/{created['connection_id']}/test")
    assert response.status_code == 401
    refreshed = client.get(f"/api/v1/connections/{created['connection_id']}").json()
    assert refreshed["status"] == "failed"
    assert refreshed["last_error"]


def test_tenant_cannot_see_other_tenants_connection(db, tenant, other_tenant):
    from app.connectors.bootstrap import persist_registry

    persist_registry(db)
    db.commit()
    with TestClient(app) as test_client:
        test_client.headers.update({"X-Tenant-Id": tenant.id, "X-User-Role": "admin"})
        created = test_client.post(
            "/api/v1/connections",
            json={"connector_id": "github", "display_name": "A", "credentials": {"token": "t"}},
        ).json()

    with TestClient(app) as other_client:
        other_client.headers.update({"X-Tenant-Id": other_tenant.id, "X-User-Role": "admin"})
        response = other_client.get(f"/api/v1/connections/{created['connection_id']}")
        assert response.status_code == 404
        assert other_client.get("/api/v1/connections").json() == []


def test_revoke_connection(client):
    created = client.post(
        "/api/v1/connections",
        json={"connector_id": "github", "display_name": "Rev", "credentials": {"token": "t"}},
    ).json()
    response = client.post(f"/api/v1/connections/{created['connection_id']}/revoke")
    assert response.status_code == 200
    assert response.json()["status"] == "revoked"


def test_discovery_assessment_and_inventory_import(client):
    response = client.post(
        "/api/v1/discovery/assessments",
        json={"application_name": "Salesforce", "vendor": "Salesforce", "openapi_available": True},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["integration_class"] == "PREBUILT_CONNECTOR_AVAILABLE"

    inventory = "name,vendor\nAcme Proprietary ERP,Acme Corp\nCanary Historian,Canary Labs\n"
    response = client.post(
        "/api/v1/discovery/inventory",
        files={"file": ("inventory.csv", inventory, "text/csv")},
    )
    assert response.status_code == 201
    names = {item["application_name"] for item in response.json()}
    assert {"Acme Proprietary ERP", "Canary Historian"} <= names


def test_custom_connector_definition_validation_and_review_flow(client):
    definition = {
        "base_url": "https://api.example.com",
        "auth": {"type": "bearer_token"},
        "resources": [{"id": "items", "path": "/items"}],
    }
    response = client.post(
        "/api/v1/custom-connectors",
        json={"name": "Acme ERP", "adapter_kind": "rest", "definition": definition},
    )
    assert response.status_code == 201
    created = response.json()
    assert created["review_status"] == "draft"

    # Cannot skip review stages.
    response = client.post(
        f"/api/v1/custom-connectors/{created['id']}/transition", json={"target": "published"}
    )
    assert response.status_code == 422

    for target in ("pending_review", "approved", "published"):
        response = client.post(
            f"/api/v1/custom-connectors/{created['id']}/transition", json={"target": target}
        )
        assert response.status_code == 200
        assert response.json()["review_status"] == target


def test_custom_sql_connector_rejects_write_query(client):
    definition = {
        "dialect": "postgresql",
        "queries": [{"id": "bad", "sql": "DELETE FROM orders"}],
    }
    response = client.post(
        "/api/v1/custom-connectors",
        json={"name": "Bad SQL", "adapter_kind": "sql", "definition": definition},
    )
    assert response.status_code == 201
    assert response.json()["validation_report"]["valid"] is False
    # ...and it cannot be approved.
    created = response.json()
    client.post(f"/api/v1/custom-connectors/{created['id']}/transition", json={"target": "pending_review"})
    response = client.post(
        f"/api/v1/custom-connectors/{created['id']}/transition", json={"target": "approved"}
    )
    assert response.status_code == 422


def test_event_contract_endpoint(client):
    response = client.get("/api/v1/events/contract")
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "1.0"
    types = {item["event_type"] for item in body["event_types"]}
    assert "connector.record.observed" in types
    assert body["delivery"]["semantics"] == "at-least-once"


def test_webhook_rejects_unsigned_delivery(client, db, tenant):
    created = client.post(
        "/api/v1/connections",
        json={
            "connector_id": "universal_webhook",
            "display_name": "Inbound",
            "configuration": {
                "options": {
                    "adapter": {"signature_scheme": "sha256", "events": ["issue.created"]}
                }
            },
            "credentials": {"webhook_secret": "whsec_test"},
        },
    ).json()

    response = client.post(
        f"/api/v1/webhooks/{tenant.id}/{created['connection_id']}/github",
        json={"action": "opened"},
    )
    assert response.status_code == 401


def test_webhook_accepts_valid_signature_and_rejects_replay(client, db, tenant):
    created = client.post(
        "/api/v1/connections",
        json={
            "connector_id": "universal_webhook",
            "display_name": "Inbound",
            "configuration": {
                "options": {
                    "adapter": {"signature_scheme": "sha256", "events": ["issue.created"]}
                }
            },
            "credentials": {"webhook_secret": "whsec_test"},
        },
    ).json()

    from app.core.webhook_security import compute_hmac_sha256

    body = b'{"action":"opened"}'
    signature = compute_hmac_sha256("whsec_test", body)
    url = f"/api/v1/webhooks/{tenant.id}/{created['connection_id']}/github"
    headers = {"X-Signature-256": signature, "X-GitHub-Delivery": "delivery-1"}

    first = client.post(url, content=body, headers=headers)
    assert first.status_code == 202
    assert first.json()["status"] == "accepted"

    # Replay with the same delivery id is rejected as a duplicate.
    second = client.post(url, content=body, headers=headers)
    assert second.status_code == 202
    assert second.json()["status"] == "duplicate"
