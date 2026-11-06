"""Tenant isolation tests.

Proves one tenant cannot read, modify, sync or revoke another tenant's
connections, and that a cross-tenant attempt is recorded in the audit log
while the caller only ever sees 404.
"""

from __future__ import annotations

import pytest

from app.core.errors import NotFoundError
from app.db import models
from app.schemas.contracts import ConnectionConfiguration
from app.services.connection_service import ConnectionService


def _make_connection(db, tenant_id: str, name: str = "GitHub Prod") -> models.Connection:
    service = ConnectionService(db)
    connection = service.create_connection(
        tenant_id,
        connector_id="github",
        display_name=name,
        configuration=ConnectionConfiguration(base_url="https://api.github.com"),
        credentials={"token": "ghp_test_token"},
        actor_id="user-1",
    )
    db.commit()
    return connection


def test_connection_is_scoped_to_tenant(db, tenant, other_tenant):
    connection = _make_connection(db, tenant.id)
    service = ConnectionService(db)
    assert service.get_connection(tenant.id, connection.id).id == connection.id
    with pytest.raises(NotFoundError):
        service.get_connection(other_tenant.id, connection.id)


def test_list_connections_never_leaks(db, tenant, other_tenant):
    _make_connection(db, tenant.id, "Tenant A Conn")
    _make_connection(db, other_tenant.id, "Tenant B Conn")
    db.commit()
    service = ConnectionService(db)
    a_ids = {c.id for c in service.list_connections(tenant.id)}
    b_ids = {c.id for c in service.list_connections(other_tenant.id)}
    assert a_ids and b_ids
    assert a_ids.isdisjoint(b_ids)


def test_cross_tenant_access_is_audited(db, tenant, other_tenant):
    connection = _make_connection(db, tenant.id)
    service = ConnectionService(db)
    with pytest.raises(NotFoundError):
        service.get_connection(other_tenant.id, connection.id)
    db.commit()
    violations = (
        db.query(models.AuditLog)
        .filter(models.AuditLog.action == "tenant_isolation_violation")
        .all()
    )
    assert len(violations) == 1
    assert violations[0].resource_id == connection.id
    assert violations[0].tenant_id == other_tenant.id


def test_cannot_revoke_other_tenants_connection(db, tenant, other_tenant):
    connection = _make_connection(db, tenant.id)
    service = ConnectionService(db)
    with pytest.raises(NotFoundError):
        service.revoke(other_tenant.id, connection.id, actor_id="attacker")
    db.refresh(connection)
    assert connection.status != "revoked"


def test_credential_reference_is_tenant_scoped(db, tenant, other_tenant):
    connection = _make_connection(db, tenant.id)
    service = ConnectionService(db)
    assert service.credential_reference(tenant.id, connection.id) is not None
    assert service.credential_reference(other_tenant.id, connection.id) is None


def test_cross_tenant_credential_decryption_is_impossible(db, tenant, other_tenant):
    """Even with the row id, the ciphertext is bound to the owning tenant."""
    from app.core.crypto import CredentialDecryptionError, SealedCredential, get_cipher

    connection = _make_connection(db, tenant.id)
    credential = (
        db.query(models.Credential)
        .filter(models.Credential.connection_id == connection.id)
        .one()
    )
    sealed = SealedCredential.from_storage(
        {
            "encrypted_payload": credential.encrypted_payload,
            "nonce": credential.nonce,
            "key_version": credential.key_version,
            "algorithm": credential.algorithm,
        }
    )
    with pytest.raises(CredentialDecryptionError):
        get_cipher().open(sealed, tenant_id=other_tenant.id, connection_id=connection.id)
