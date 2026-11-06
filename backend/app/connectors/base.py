"""Connector SDK - the standard lifecycle contract.

Every connector (prebuilt, universal adapter or custom) implements
:class:`BaseConnector`.  Connector code is instantiated per call by the
connection service and never shares process state with other tenants; it
receives decrypted credentials only for the duration of an operation.

Lifecycle methods
-----------------
validate_configuration, test_connection, authenticate, refresh_credentials,
discover_capabilities, discover_resources, fetch_records,
fetch_incremental_records, subscribe_to_events, normalize_metadata,
health_check, disconnect.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

from app.schemas.contracts import (
    ConnectionConfiguration,
    ConnectorCapability,
    ConnectorHealth,
    ConnectorResource,
    ConnectorTestResult,
    FetchPage,
    NormalizedRecord,
    ValidationResult,
)


@dataclass
class ConnectorContext:
    """Everything a connector needs for one operation. Tenant-scoped."""

    tenant_id: str
    connection_id: str
    connector_id: str
    configuration: ConnectionConfiguration
    credentials: dict[str, Any] = field(default_factory=dict)
    granted_scopes: list[str] = field(default_factory=list)
    # Injected HTTP transport so tests can substitute a mock without patching.
    http_client: Any | None = None
    # Opaque per-connection settings that must never contain secrets.
    runtime_options: dict[str, Any] = field(default_factory=dict)


class BaseConnector(abc.ABC):
    """Standard connector interface.

    Subclasses declare ``connector_id`` and ``provider`` and implement the
    abstract methods.  All network egress MUST go through the injected HTTP
    client or :mod:`app.core.egress` so SSRF controls cannot be bypassed.
    """

    connector_id: str = "base"
    provider: str = "base"
    is_read_only: bool = True

    def __init__(self, context: ConnectorContext) -> None:
        self.context = context

    # -- configuration ---------------------------------------------------

    def validate_configuration(self, configuration: ConnectionConfiguration) -> ValidationResult:
        """Cheap, offline validation of the supplied configuration."""
        errors: list[str] = []
        if not configuration.base_url and not configuration.host:
            # Many connectors are pure-API and derive the host from the provider.
            pass
        return ValidationResult(valid=not errors, errors=errors)

    # -- authentication --------------------------------------------------

    @abc.abstractmethod
    async def test_connection(self) -> ConnectorTestResult:
        """Perform a minimal authenticated call. Must not mutate remote state."""

    async def authenticate(self) -> None:
        """Acquire/refresh an access token if the provider requires one.

        Connectors using static credentials (API keys, PATs) rely on the
        default no-op implementation.
        """
        return None

    async def refresh_credentials(self) -> dict[str, Any] | None:
        """Return refreshed credential material to be re-sealed, or None.

        A returned dict replaces the stored credential payload.  The connection
        service re-encrypts it; connectors never persist secrets themselves.
        """
        return None

    # -- discovery -------------------------------------------------------

    def discover_capabilities(self) -> list[ConnectorCapability]:
        """Capabilities this connector actually supports."""
        return []

    @abc.abstractmethod
    async def discover_resources(self) -> list[ConnectorResource]:
        """Enumerate only the resources the granted scopes authorise."""

    # -- data access -----------------------------------------------------

    @abc.abstractmethod
    async def fetch_records(
        self, resource_id: str, *, cursor: str | None = None, page_size: int | None = None
    ) -> FetchPage:
        """Fetch a page of records for a resource."""

    async def fetch_incremental_records(
        self,
        resource_id: str,
        *,
        cursor: str | None = None,
        watermark: Any | None = None,
        page_size: int | None = None,
    ) -> FetchPage:
        """Fetch records changed since ``watermark``. Defaults to full fetch."""
        return await self.fetch_records(resource_id, cursor=cursor, page_size=page_size)

    async def subscribe_to_events(self, resource_id: str) -> dict[str, Any] | None:
        """Register a webhook subscription. Returns subscription metadata."""
        return None

    # -- transformation --------------------------------------------------

    def normalize_metadata(
        self, raw: dict[str, Any], *, resource_id: str
    ) -> NormalizedRecord:
        """Convert one provider record into the standard normalized shape."""
        source_id = str(
            raw.get("id") or raw.get("_id") or raw.get("key") or raw.get("uuid") or ""
        )
        return NormalizedRecord(
            source_record_id=source_id,
            resource_id=resource_id,
            source_metadata={"provider": self.provider, "connector_id": self.connector_id},
            payload=raw,
        )

    # -- lifecycle -------------------------------------------------------

    async def health_check(self) -> ConnectorHealth:
        """Cheap liveness probe; defaults to a full connection test."""
        result = await self.test_connection()
        from app.schemas.contracts import HealthStatus

        return ConnectorHealth(
            status=HealthStatus.HEALTHY if result.success else HealthStatus.UNHEALTHY,
            latency_ms=result.latency_ms,
            message=result.message,
        )

    async def disconnect(self) -> None:
        """Release remote subscriptions / tokens where the provider allows it."""
        return None
