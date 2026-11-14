"""Self-scoped membership listing (``GET /tenants/memberships``).

The endpoint exists so a user who belongs to more than one organization can be
offered a choice of tenant.  The claim under test is that it is *self-scoped*:
a caller can only ever see their own memberships, and only within active
tenants.  It is not a directory of an organization's users — that is the
separate, admin-only ``GET /tenants/{tenant_id}/memberships``.

As in ``test_authorization.py``, tokens are genuinely signed with a real RSA
key and verified against a real JWKS server.  Nothing in the verification path
is mocked.
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


def _member(db, tenant, subject, role, *, email=None, is_active=True, issuer=ISSUER):
    row = models.User(
        id=str(uuid.uuid4()),
        tenant_id=tenant.id,
        email=email or f"{subject}@example.test",
        display_name=subject,
        role=role,
        is_active=is_active,
        external_issuer=issuer,
        external_subject=subject,
    )
    db.add(row)
    db.commit()
    return row


def _auth(subject: str, key: SigningKey, **headers) -> dict:
    token = key.sign(authkit.claims(sub=subject))
    return {"Authorization": f"Bearer {token}", **headers}


MEMBERSHIPS = "/api/v1/tenants/memberships"


# ---------------------------------------------------------------------------
# Authentication is required
# ---------------------------------------------------------------------------


def test_anonymous_request_is_rejected(oidc):
    """No token at all is a 401, never an empty list."""
    from app.main import app

    with TestClient(app) as client:
        response = client.get(MEMBERSHIPS)
    assert response.status_code == 401


def test_invalid_token_is_rejected(oidc, signing_key):
    """A token signed by the wrong key is not an identity."""
    from app.main import app

    other = SigningKey(kid="other-key")
    with TestClient(app) as client:
        response = client.get(MEMBERSHIPS, headers=_auth("user-a", other))
    assert response.status_code == 401


def test_unknown_subject_gets_an_empty_list(oidc, db, tenant, signing_key):
    """A valid identity that belongs nowhere is authenticated, not forbidden.

    The endpoint answers "you have no organizations", which is both accurate
    and free of information about anyone else.  The frontend turns this into an
    explicit no-access screen rather than a login loop.
    """
    from app.main import app

    with TestClient(app) as client:
        response = client.get(MEMBERSHIPS, headers=_auth("nobody-here", signing_key))
    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# Self-scoping: you see your own memberships, and only those
# ---------------------------------------------------------------------------


def test_returns_only_own_memberships(oidc, db, tenant, other_tenant, signing_key):
    """Two people in one tenant: each sees exactly their own row."""
    from app.main import app

    _member(db, tenant, "alice", "owner")
    _member(db, tenant, "bob", "member", email="bob@example.test")

    with TestClient(app) as client:
        alice = client.get(MEMBERSHIPS, headers=_auth("alice", signing_key))
        bob = client.get(MEMBERSHIPS, headers=_auth("bob", signing_key))

    assert alice.status_code == 200
    assert bob.status_code == 200
    # Neither sees the other's row.
    assert [m["role"] for m in alice.json()] == ["owner"]
    assert [m["role"] for m in bob.json()] == ["member"]


def test_returns_all_memberships_across_tenants(oidc, db, tenant, other_tenant, signing_key):
    """A genuine multi-org user sees every tenant they belong to."""
    from app.main import app

    _member(db, tenant, "multi", "owner", email="m1@example.test")
    _member(db, other_tenant, "multi", "viewer", email="m2@example.test")

    with TestClient(app) as client:
        response = client.get(MEMBERSHIPS, headers=_auth("multi", signing_key))

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert {m["tenant_id"] for m in body} == {tenant.id, other_tenant.id}
    assert {m["role"] for m in body} == {"owner", "viewer"}


def test_cannot_see_another_users_memberships(oidc, db, tenant, other_tenant, signing_key):
    """There is no parameter to widen the query, so another user's rows never appear."""
    from app.main import app

    _member(db, tenant, "alice", "owner")
    _member(db, other_tenant, "mallory", "owner", email="mallory@example.test")

    with TestClient(app) as client:
        response = client.get(MEMBERSHIPS, headers=_auth("alice", signing_key))

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["tenant_id"] == tenant.id


def test_does_not_leak_other_members_of_same_tenant(oidc, db, tenant, signing_key):
    """It is a self-read, not an organization directory: no colleague rows."""
    from app.main import app

    _member(db, tenant, "alice", "owner")
    for i in range(3):
        _member(db, tenant, f"colleague-{i}", "member", email=f"c{i}@example.test")

    with TestClient(app) as client:
        response = client.get(MEMBERSHIPS, headers=_auth("alice", signing_key))

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_response_exposes_no_other_member_data(oidc, db, tenant, signing_key):
    """The payload is deliberately narrow — no email, display name, or subject."""
    from app.main import app

    _member(db, tenant, "alice", "owner")

    with TestClient(app) as client:
        response = client.get(MEMBERSHIPS, headers=_auth("alice", signing_key))

    row = response.json()[0]
    assert set(row) == {"tenant_id", "tenant_name", "tenant_slug", "role"}
    for forbidden in ("email", "display_name", "external_subject", "external_issuer"):
        assert forbidden not in row


# ---------------------------------------------------------------------------
# Active-only, and issuer-scoped
# ---------------------------------------------------------------------------


def test_inactive_membership_is_excluded(oidc, db, tenant, other_tenant, signing_key):
    """A deactivated membership is not offered as a tenant choice."""
    from app.main import app

    _member(db, tenant, "multi", "owner", email="m1@example.test")
    _member(db, other_tenant, "multi", "viewer", email="m2@example.test", is_active=False)

    with TestClient(app) as client:
        response = client.get(MEMBERSHIPS, headers=_auth("multi", signing_key))

    assert response.status_code == 200
    assert [m["tenant_id"] for m in response.json()] == [tenant.id]


def test_membership_in_inactive_tenant_is_excluded(oidc, db, tenant, other_tenant, signing_key):
    """A membership in a deactivated organization is not offered either."""
    from app.main import app

    _member(db, tenant, "multi", "owner", email="m1@example.test")
    _member(db, other_tenant, "multi", "viewer", email="m2@example.test")
    other_tenant.is_active = False
    db.commit()

    with TestClient(app) as client:
        response = client.get(MEMBERSHIPS, headers=_auth("multi", signing_key))

    assert response.status_code == 200
    assert [m["tenant_id"] for m in response.json()] == [tenant.id]


def test_subject_from_a_different_issuer_is_not_matched(oidc, db, tenant, signing_key):
    """Same ``sub`` string from another issuer must not resolve to this row.

    Two providers can legitimately issue the same subject string; matching on
    ``sub`` alone would let one provider's user claim another's membership.
    """
    from app.main import app

    _member(db, tenant, "shared-sub", "owner", issuer="https://other-idp.test/")

    with TestClient(app) as client:
        response = client.get(MEMBERSHIPS, headers=_auth("shared-sub", signing_key))

    # The token's issuer is the trusted one, so this subject holds nothing here.
    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# Selection is a convenience, never an authorization
# ---------------------------------------------------------------------------


def test_reachable_before_a_tenant_is_chosen(oidc, db, tenant, other_tenant, signing_key):
    """A multi-organization user can discover their tenants before selecting one.

    This is the reason the endpoint uses subject-only authentication: resolving
    a full principal would refuse this request as ambiguous, leaving the user
    unable to learn which ``X-Tenant-Id`` values are valid for them.
    """
    from app.main import app

    _member(db, tenant, "multi", "owner", email="m1@example.test")
    _member(db, other_tenant, "multi", "viewer", email="m2@example.test")

    with TestClient(app) as client:
        # No X-Tenant-Id: a tenant-scoped endpoint would answer 403 here.
        scoped = client.get("/api/v1/tenants/whoami", headers=_auth("multi", signing_key))
        listing = client.get(MEMBERSHIPS, headers=_auth("multi", signing_key))

    assert scoped.status_code == 403
    assert listing.status_code == 200
    assert len(listing.json()) == 2


def test_membership_list_does_not_grant_access_to_a_foreign_tenant(
    oidc, db, tenant, other_tenant, signing_key
):
    """Learning a tenant id from this endpoint confers no access to it."""
    from app.main import app

    _member(db, tenant, "alice", "owner")
    _member(db, other_tenant, "bob", "owner", email="bob@example.test")

    with TestClient(app) as client:
        listing = client.get(MEMBERSHIPS, headers=_auth("alice", signing_key))
        assert [m["tenant_id"] for m in listing.json()] == [tenant.id]

        # Alice knows Globex exists but cannot act there.
        denied = client.get(
            "/api/v1/connections",
            headers=_auth("alice", signing_key, **{"X-Tenant-Id": other_tenant.id}),
        )
    assert denied.status_code == 403


def test_self_read_is_scoped_but_the_admin_listing_is_unchanged(
    oidc, db, tenant, signing_key
):
    """The new self-read must not widen the existing listing endpoint.

    ``GET /tenants/{id}/memberships`` is the administrative listing: it returns
    every member of the tenant.  It is deliberately left exactly as it was, and
    the self-read above is a separate, narrower route.
    """
    from app.main import app

    _member(db, tenant, "plain-member", "viewer")
    _member(db, tenant, "someone-else", "member", email="other@example.test")

    with TestClient(app) as client:
        mine = client.get(MEMBERSHIPS, headers=_auth("plain-member", signing_key))
        listing = client.get(
            f"/api/v1/tenants/{tenant.id}/memberships",
            headers=_auth("plain-member", signing_key),
        )

    # Self-read: one row, no colleague data.
    assert mine.status_code == 200
    assert len(mine.json()) == 1
    # Administrative listing: unchanged, still returns the whole tenant.
    assert listing.status_code == 200
    assert len(listing.json()) == 2


def test_self_read_cannot_reach_another_tenant(oidc, db, tenant, other_tenant, signing_key):
    """Requesting the admin listing for a foreign tenant is refused."""
    from app.main import app

    _member(db, tenant, "alice", "owner")

    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/tenants/{other_tenant.id}/memberships",
            headers=_auth("alice", signing_key),
        )
    assert response.status_code == 403
