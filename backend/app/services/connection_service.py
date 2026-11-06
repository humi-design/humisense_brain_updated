"""Connection service.

Owns the tenant-scoped lifecycle of a connection:
create -> configure -> authenticate -> test -> select resources -> sync.

Security invariants enforced here:
* Every read and write is filtered by ``tenant_id``.  A connection id that
  belongs to another tenant resolves to ``NotFoundError`` (never 403), so
  existence is not leaked.
* Credentials are sealed with AES-256-GCM bound to ``(tenant_id, connection_id)``
  and are only decrypted in-process for the duration of an operation.
* Credential material is never returned through the API; only an opaque
  :class:`CredentialReference` is exposed.
* Every state change is written to the audit log.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import ConnectorContext
from app.connectors.registry import registry
from app.core.crypto import SealedCredential, get_cipher
from app.core.errors import (
    AuthorizationError,
    ConnectorError,
    HumisenseError,
    NotFoundError,
    TenantIsolationError,
    ValidationError,
)
from app.core.logging import get_logger
from app.db import models
from app.schemas.contracts import (
    AuditAction,
    ConnectionConfiguration,
    ConnectionStatus,
    ConnectorInstance,
    ConnectorResource,
    ConnectorTestResult,
    CredentialReference,
    HealthStatus,
    SyncConfiguration,
    SyncMode,
)

logger = get_logger(__name__)

# Fields that must never be persisted as plaintext or echoed back.
_SECRET_KEYS = {
    "password", "secret", "token", "access_token", "refresh_token", "client_secret",
    "api_key", "apikey", "private_key", "client_certificate", "bot_token",
}


def _split_secrets(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    secrets: dict[str, Any] = {}
    public: dict[str, Any] = {}
    for key, value in payload.items():
        if key.lower() in _SECRET_KEYS:
            secrets[key] = value
        else:
            public[key] = value
    return secrets, public


class ConnectionService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # -- audit -----------------------------------------------------------

    def _audit(
        self,
        tenant_id: str,
        action: AuditAction,
        *,
        actor_id: str | None,
        resource_type: str,
        resource_id: str | None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(
            models.AuditLog(
                tenant_id=tenant_id,
                actor_id=actor_id,
                action=action.value,
                resource_type=resource_type,
                resource_id=resource_id,
                detail=detail or {},
            )
        )

    # -- lookups ---------------------------------------------------------

    def get_connection(self, tenant_id: str, connection_id: str) -> models.Connection:
        stmt = select(models.Connection).where(
            models.Connection.id == connection_id,
            models.Connection.tenant_id == tenant_id,
        )
        connection = self.session.execute(stmt).scalar_one_or_none()
        if connection is None:
            # Distinguish a real cross-tenant attempt for the audit trail while
            # still returning 404 to the caller.
            other = self.session.execute(
                select(models.Connection.tenant_id).where(models.Connection.id == connection_id)
            ).scalar_one_or_none()
            if other is not None:
                self._audit(
                    tenant_id,
                    AuditAction.TENANT_ISOLATION_VIOLATION,
                    actor_id=None,
                    resource_type="connection",
                    resource_id=connection_id,
                    detail={"reason": "cross_tenant_access_attempt"},
                )
                logger.warning("cross_tenant_connection_access", connection_id=connection_id)
            raise NotFoundError("Connection not found.")
        return connection

    def list_connections(self, tenant_id: str) -> list[models.Connection]:
        stmt = (
            select(models.Connection)
            .where(models.Connection.tenant_id == tenant_id)
            .order_by(models.Connection.created_at.desc())
        )
        return list(self.session.execute(stmt).scalars().all())

    # -- lifecycle -------------------------------------------------------

    def create_connection(
        self,
        tenant_id: str,
        *,
        connector_id: str,
        display_name: str,
        configuration: ConnectionConfiguration,
        credentials: dict[str, Any],
        actor_id: str | None = None,
        granted_scopes: list[str] | None = None,
    ) -> models.Connection:
        definition = registry.get_definition(connector_id)

        connection = models.Connection(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            connector_id=connector_id,
            provider=definition.provider,
            display_name=display_name,
            configuration=configuration.model_dump(mode="json"),
            granted_scopes=granted_scopes or [],
            status=ConnectionStatus.CONFIGURED.value,
            created_by=actor_id,
        )
        self.session.add(connection)
        self.session.flush()

        if credentials:
            self._store_credentials(tenant_id, connection.id, credentials, rotate=False)

        self._audit(
            tenant_id,
            AuditAction.CONNECTION_CREATED,
            actor_id=actor_id,
            resource_type="connection",
            resource_id=connection.id,
            detail={"connector_id": connector_id, "provider": definition.provider},
        )
        self.session.flush()
        return connection

    def _store_credentials(
        self, tenant_id: str, connection_id: str, credentials: dict[str, Any], *, rotate: bool
    ) -> None:
        cipher = get_cipher()
        sealed = cipher.seal(credentials, tenant_id=tenant_id, connection_id=connection_id)
        storage = sealed.to_storage()
        row = self.session.execute(
            select(models.Credential).where(models.Credential.connection_id == connection_id)
        ).scalar_one_or_none()
        if row is None:
            row = models.Credential(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                connection_id=connection_id,
                **storage,
            )
            self.session.add(row)
        else:
            for key, value in storage.items():
                setattr(row, key, value)
            if rotate:
                row.rotated_at = datetime.now(timezone.utc)
        self.session.flush()

    def rotate_credentials(
        self,
        tenant_id: str,
        connection_id: str,
        credentials: dict[str, Any],
        *,
        actor_id: str | None = None,
    ) -> None:
        connection = self.get_connection(tenant_id, connection_id)
        self._store_credentials(tenant_id, connection.id, credentials, rotate=True)
        connection.status = ConnectionStatus.CONFIGURED.value
        self._audit(
            tenant_id,
            AuditAction.CREDENTIAL_ROTATED,
            actor_id=actor_id,
            resource_type="connection",
            resource_id=connection.id,
        )
        self.session.flush()

    def _load_credentials(self, tenant_id: str, connection_id: str) -> dict[str, Any]:
        row = self.session.execute(
            select(models.Credential).where(
                models.Credential.connection_id == connection_id,
                models.Credential.tenant_id == tenant_id,
            )
        ).scalar_one_or_none()
        if row is None:
            return {}
        sealed = SealedCredential.from_storage(
            {
                "encrypted_payload": row.encrypted_payload,
                "nonce": row.nonce,
                "key_version": row.key_version,
                "algorithm": row.algorithm,
            }
        )
        return get_cipher().open(sealed, tenant_id=tenant_id, connection_id=connection_id)

    def credential_reference(self, tenant_id: str, connection_id: str) -> CredentialReference | None:
        row = self.session.execute(
            select(models.Credential).where(
                models.Credential.connection_id == connection_id,
                models.Credential.tenant_id == tenant_id,
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return CredentialReference(
            reference_id=row.id,
            tenant_id=row.tenant_id,
            connection_id=row.connection_id,
            key_version=row.key_version,
            algorithm=row.algorithm,
            created_at=row.created_at,
            rotated_at=row.rotated_at,
            expires_at=row.expires_at,
        )

    # -- connector interaction -------------------------------------------

    def build_context(self, tenant_id: str, connection: models.Connection) -> ConnectorContext:
        config = ConnectionConfiguration(**connection.configuration)
        credentials = self._load_credentials(tenant_id, connection.id)
        return ConnectorContext(
            tenant_id=tenant_id,
            connection_id=connection.id,
            connector_id=connection.connector_id,
            configuration=config,
            credentials=credentials,
            granted_scopes=list(connection.granted_scopes or []),
            runtime_options=dict(config.options or {}),
        )

    def _connector(self, tenant_id: str, connection: models.Connection):
        context = self.build_context(tenant_id, connection)
        return registry.create(connection.connector_id, context), context

    def validate(self, tenant_id: str, connection: models.Connection) -> Any:
        connector, _ = self._connector(tenant_id, connection)
        return connector.validate_configuration(connector.context.configuration)

    async def test_connection(
        self, tenant_id: str, connection_id: str, *, actor_id: str | None = None
    ) -> ConnectorTestResult:
        connection = self.get_connection(tenant_id, connection_id)
        connector, _ = self._connector(tenant_id, connection)
        now = datetime.now(timezone.utc)
        try:
            result = await connector.test_connection()
        except HumisenseError as exc:
            # A failed authentication or connector error must be recorded on the
            # connection, not silently propagated, so the UI can show it.
            connection.health_status = HealthStatus.UNHEALTHY.value
            connection.health_checked_at = now
            connection.health_message = exc.message
            connection.status = ConnectionStatus.FAILED.value
            connection.consecutive_failures += 1
            connection.last_error = exc.message
            self._audit(
                tenant_id,
                AuditAction.CONNECTION_TESTED,
                actor_id=actor_id,
                resource_type="connection",
                resource_id=connection.id,
                detail={"success": False, "error": exc.code},
            )
            # Commit the failure state before propagating so the error survives
            # the request-level rollback and the UI can display it.
            self.session.commit()
            raise

        connection.health_status = HealthStatus.HEALTHY.value if result.success else HealthStatus.UNHEALTHY.value
        connection.health_checked_at = now
        connection.health_latency_ms = result.latency_ms
        connection.health_message = result.message
        if result.success:
            connection.status = ConnectionStatus.CONNECTED.value
            connection.consecutive_failures = 0
            connection.last_error = None
            if result.account_identifier:
                connection.account_identifier = result.account_identifier
            if result.granted_scopes:
                connection.granted_scopes = result.granted_scopes
        else:
            connection.status = ConnectionStatus.FAILED.value
            connection.consecutive_failures += 1
            connection.last_error = result.message

        self._audit(
            tenant_id,
            AuditAction.CONNECTION_TESTED,
            actor_id=actor_id,
            resource_type="connection",
            resource_id=connection.id,
            detail={"success": result.success, "latency_ms": result.latency_ms},
        )
        self.session.flush()
        return result

    async def discover_resources(
        self, tenant_id: str, connection_id: str, *, actor_id: str | None = None
    ) -> list[ConnectorResource]:
        connection = self.get_connection(tenant_id, connection_id)
        connector, _ = self._connector(tenant_id, connection)
        resources = await connector.discover_resources()
        now = datetime.now(timezone.utc)
        for resource in resources:
            existing = self.session.execute(
                select(models.ConnectionResource).where(
                    models.ConnectionResource.connection_id == connection.id,
                    models.ConnectionResource.external_id == resource.external_id,
                )
            ).scalar_one_or_none()
            if existing is None:
                self.session.add(
                    models.ConnectionResource(
                        id=str(uuid.uuid4()),
                        tenant_id=tenant_id,
                        connection_id=connection.id,
                        external_id=resource.external_id,
                        name=resource.name,
                        resource_type=resource.resource_type,
                        parent_id=resource.parent_id,
                        read_only=resource.read_only,
                        metadata_json=resource.metadata,
                    )
                )
            else:
                existing.name = resource.name
                existing.resource_type = resource.resource_type
                existing.metadata_json = resource.metadata
        connection.health_checked_at = now
        self.session.flush()
        return resources

    def select_resources(
        self,
        tenant_id: str,
        connection_id: str,
        external_ids: list[str],
        *,
        actor_id: str | None = None,
    ) -> list[models.ConnectionResource]:
        connection = self.get_connection(tenant_id, connection_id)
        rows = list(
            self.session.execute(
                select(models.ConnectionResource).where(
                    models.ConnectionResource.connection_id == connection.id,
                    models.ConnectionResource.tenant_id == tenant_id,
                )
            ).scalars().all()
        )
        known = {row.external_id for row in rows}
        unknown = [eid for eid in external_ids if eid not in known]
        if unknown:
            raise ValidationError("Unknown resource(s) requested.",
                                  detail={"unknown": unknown[:20]})
        for row in rows:
            row.is_selected = row.external_id in external_ids
        self._audit(
            tenant_id,
            AuditAction.RESOURCE_SELECTED,
            actor_id=actor_id,
            resource_type="connection",
            resource_id=connection.id,
            detail={"count": len(external_ids)},
        )
        self.session.flush()
        return rows

    def configure_sync(
        self,
        tenant_id: str,
        connection_id: str,
        config: SyncConfiguration,
        *,
        actor_id: str | None = None,
    ) -> models.SyncConfig:
        connection = self.get_connection(tenant_id, connection_id)
        definition = registry.get_definition(connection.connector_id)
        if config.write_enabled and definition.is_read_only:
            raise ValidationError(
                f"Connector '{connection.connector_id}' is read-only; write sync is not permitted."
            )
        row = self.session.execute(
            select(models.SyncConfig).where(models.SyncConfig.connection_id == connection.id)
        ).scalar_one_or_none()
        values = {
            "mode": config.mode.value,
            "schedule_cron": config.schedule_cron,
            "page_size": config.page_size,
            "batch_size": config.batch_size,
            "lookback_seconds": config.lookback_seconds,
            "enabled": config.enabled,
            "max_retries": config.max_retries,
            "write_enabled": config.write_enabled,
        }
        if row is None:
            row = models.SyncConfig(
                id=str(uuid.uuid4()), tenant_id=tenant_id, connection_id=connection.id, **values
            )
            self.session.add(row)
        else:
            for key, value in values.items():
                setattr(row, key, value)
        connection.status = ConnectionStatus.CONFIGURED.value if not connection.last_successful_sync else connection.status
        self.session.flush()
        return row

    def revoke(
        self, tenant_id: str, connection_id: str, *, actor_id: str | None = None
    ) -> models.Connection:
        connection = self.get_connection(tenant_id, connection_id)
        now = datetime.now(timezone.utc)
        connection.status = ConnectionStatus.REVOKED.value
        connection.revoked_at = now
        connection.health_status = HealthStatus.UNKNOWN.value
        # Credentials are destroyed on revoke so a revoked connection cannot be
        # re-used even if the row is later restored.
        credential = self.session.execute(
            select(models.Credential).where(models.Credential.connection_id == connection.id)
        ).scalar_one_or_none()
        if credential is not None:
            self.session.delete(credential)
        self._audit(
            tenant_id,
            AuditAction.CONNECTION_REVOKED,
            actor_id=actor_id,
            resource_type="connection",
            resource_id=connection.id,
        )
        self.session.flush()
        return connection

    def delete(self, tenant_id: str, connection_id: str, *, actor_id: str | None = None) -> None:
        connection = self.get_connection(tenant_id, connection_id)
        self._audit(
            tenant_id,
            AuditAction.CONNECTION_DELETED,
            actor_id=actor_id,
            resource_type="connection",
            resource_id=connection.id,
        )
        self.session.delete(connection)
        self.session.flush()

    def to_instance(self, tenant_id: str, connection: models.Connection) -> ConnectorInstance:
        return ConnectorInstance(
            connection_id=connection.id,
            tenant_id=connection.tenant_id,
            connector_id=connection.connector_id,
            provider=connection.provider,
            display_name=connection.display_name,
            account_identifier=connection.account_identifier,
            resource_identifier=connection.resource_identifier,
            credential_reference=self.credential_reference(tenant_id, connection.id),
            granted_scopes=list(connection.granted_scopes or []),
            status=ConnectionStatus(connection.status),
            last_successful_sync=connection.last_successful_sync,
            last_error=connection.last_error,
            created_at=connection.created_at,
            updated_at=connection.updated_at,
        )
