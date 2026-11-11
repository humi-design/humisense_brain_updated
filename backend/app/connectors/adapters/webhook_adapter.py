"""Universal webhook receiver connector.

The webhook adapter does not poll a provider.  Instead, inbound deliveries are
verified by the webhook service and pushed here as normalized records.  This
connector exposes the verification scheme and resource metadata so the rest of
the system treats webhooks exactly like any other connector.
"""

from __future__ import annotations

from typing import Any

from app.connectors.base import BaseConnector, ConnectorContext
from app.schemas.contracts import (
    Capability,
    ConnectionConfiguration,
    ConnectorCapability,
    ConnectorResource,
    ConnectorTestResult,
    FetchPage,
    NormalizedRecord,
    ValidationResult,
)


class WebhookAdapterConnector(BaseConnector):
    connector_id = "universal_webhook"
    provider = "humisense"
    is_read_only = True

    def _adapter(self) -> dict[str, Any]:
        return dict(self.context.configuration.options.get("adapter") or {})

    def validate_configuration(self, configuration: ConnectionConfiguration) -> ValidationResult:
        adapter = self._adapter()
        errors: list[str] = []
        scheme = str(adapter.get("signature_scheme", "sha256")).lower()
        if scheme in {"none", ""}:
            errors.append("A signature scheme is required; unsigned webhooks are rejected.")
        if not adapter.get("events"):
            errors.append("At least one event type must be declared.")
        return ValidationResult(valid=not errors, errors=errors)

    def discover_capabilities(self) -> list[ConnectorCapability]:
        return [
            ConnectorCapability(capability=Capability.WEBHOOK),
            ConnectorCapability(capability=Capability.READ),
        ]

    async def test_connection(self) -> ConnectorTestResult:
        return ConnectorTestResult(
            success=True,
            message="Webhook endpoint is active; awaiting signed deliveries.",
            details={
                "signature_scheme": self._adapter().get("signature_scheme", "sha256"),
                "events": self._adapter().get("events", []),
            },
        )

    async def discover_resources(self) -> list[ConnectorResource]:
        return [
            ConnectorResource(
                external_id=event,
                name=event,
                resource_type="webhook_event",
                read_only=True,
            )
            for event in self._adapter().get("events", [])
        ]

    async def fetch_records(
        self, resource_id: str, *, cursor: str | None = None, page_size: int | None = None
    ) -> FetchPage:
        # Webhook events arrive via HTTP; polling returns nothing by design.
        return FetchPage(records=[], next_cursor=None, has_more=False)
