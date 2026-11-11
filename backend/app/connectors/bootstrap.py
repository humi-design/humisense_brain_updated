"""Bootstrap the connector registry with catalogue entries and factories."""

from __future__ import annotations

from app.connectors.catalogue import build_adapter_definitions, build_catalogue
from app.connectors.registry import ConnectorRegistry, _make_factory

# (connector_id -> (module, class)) for everything that has working code.
_FACTORIES: dict[str, tuple[str, str]] = {
    # Universal adapters
    "universal_rest": ("app.connectors.adapters.rest_adapter", "RestAdapterConnector"),
    "universal_graphql": ("app.connectors.adapters.graphql_adapter", "GraphQLAdapterConnector"),
    "universal_sql": ("app.connectors.adapters.sql_adapter", "SqlAdapterConnector"),
    "universal_file": ("app.connectors.adapters.file_adapter", "FileAdapterConnector"),
    "universal_webhook": ("app.connectors.adapters.webhook_adapter", "WebhookAdapterConnector"),
    # Prebuilt connectors with real implementations
    "github": ("app.connectors.providers.github_connector", "GitHubConnector"),
    "slack": ("app.connectors.providers.slack_connector", "SlackConnector"),
    "canary_labs": ("app.connectors.providers.canary_connector", "CanaryConnector"),
}


def bootstrap_registry(registry: ConnectorRegistry) -> None:
    for definition in build_catalogue() + build_adapter_definitions():
        factory = None
        target = _FACTORIES.get(definition.connector_id)
        if target is not None:
            factory = _make_factory(*target)
        registry.register(definition, factory)


def persist_registry(session) -> int:  # noqa: ANN001
    """Mirror the in-process catalogue into the ``connector_registrations`` table.

    The registry table is the durable record of which connectors exist, their
    maturity and their configuration schema.  It is global (not tenant-scoped)
    and is refreshed on startup.
    """
    from sqlalchemy import select

    from app.connectors.registry import registry as _registry
    from app.db import models

    count = 0
    for definition in _registry.list_definitions():
        row = session.execute(
            select(models.ConnectorRegistration).where(
                models.ConnectorRegistration.id == definition.connector_id
            )
        ).scalar_one_or_none()
        payload = definition.model_dump(mode="json")
        installable = _registry.is_installable(definition.connector_id)
        if row is None:
            row = models.ConnectorRegistration(id=definition.connector_id)
            session.add(row)
        row.provider = definition.provider
        row.display_name = definition.display_name
        row.category = definition.category.value
        row.version = definition.version
        row.implementation_state = definition.implementation_state.value
        row.definition = payload
        row.is_installable = installable
        count += 1
    session.flush()
    return count
