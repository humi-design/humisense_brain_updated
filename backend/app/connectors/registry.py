"""Central connector registry.

Holds every connector *definition* (prebuilt, universal adapter or custom) and
instantiates the matching connector class.  The registry is the single place
that knows which connectors exist and how mature each one is.

Status model
------------
A definition being present in the catalogue does NOT mean a tenant is
connected.  The registry exposes the static catalogue; the connection service
owns per-tenant lifecycle state (configured -> authenticated -> connected ->
synchronizing -> healthy / degraded / failed / revoked).
"""

from __future__ import annotations

from collections.abc import Callable

from app.connectors.base import BaseConnector, ConnectorContext
from app.core.errors import NotFoundError
from app.schemas.contracts import (
    ConnectorCategory,
    ConnectorDefinition,
    ImplementationState,
)

ConnectorFactory = Callable[[ConnectorContext], BaseConnector]


class ConnectorRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, ConnectorDefinition] = {}
        self._factories: dict[str, ConnectorFactory] = {}

    def register(
        self, definition: ConnectorDefinition, factory: ConnectorFactory | None = None
    ) -> None:
        self._definitions[definition.connector_id] = definition
        if factory is not None:
            self._factories[definition.connector_id] = factory

    def unregister(self, connector_id: str) -> None:
        self._definitions.pop(connector_id, None)
        self._factories.pop(connector_id, None)

    def get_definition(self, connector_id: str) -> ConnectorDefinition:
        definition = self._definitions.get(connector_id)
        if definition is None:
            raise NotFoundError(f"Connector '{connector_id}' is not registered.")
        return definition

    def list_definitions(
        self,
        *,
        category: ConnectorCategory | None = None,
        search: str | None = None,
        installable_only: bool = False,
    ) -> list[ConnectorDefinition]:
        results = list(self._definitions.values())
        if category is not None:
            results = [d for d in results if d.category == category]
        if installable_only:
            results = [d for d in results if d.connector_id in self._factories]
        if search:
            needle = search.lower()
            results = [
                d
                for d in results
                if needle in d.display_name.lower()
                or needle in d.provider.lower()
                or needle in d.description.lower()
            ]
        return sorted(results, key=lambda d: d.display_name.lower())

    def is_installable(self, connector_id: str) -> bool:
        return connector_id in self._factories

    def create(self, connector_id: str, context: ConnectorContext) -> BaseConnector:
        factory = self._factories.get(connector_id)
        if factory is None:
            definition = self.get_definition(connector_id)
            raise NotFoundError(
                f"Connector '{connector_id}' is catalogued "
                f"({definition.implementation_state.value}) but not yet installable."
            )
        return factory(context)

    def implementation_state(self, connector_id: str) -> ImplementationState:
        return self.get_definition(connector_id).implementation_state


registry = ConnectorRegistry()


def _make_factory(module: str, class_name: str) -> ConnectorFactory:
    """Lazy factory so importing the registry does not import every connector."""

    def factory(context: ConnectorContext) -> BaseConnector:
        import importlib

        module_obj = importlib.import_module(module)
        cls = getattr(module_obj, class_name)
        return cls(context)

    return factory
