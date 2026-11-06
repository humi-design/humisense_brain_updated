"""Connector catalogue and registry endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import CurrentPrincipal
from app.api.schemas import ConnectorDefinitionOut
from app.connectors.registry import registry
from app.schemas.contracts import ConnectorCategory

router = APIRouter(prefix="/connectors", tags=["connectors"])


@router.get("", response_model=list[ConnectorDefinitionOut])
def list_connectors(
    principal: CurrentPrincipal,
    category: ConnectorCategory | None = None,
    search: str | None = Query(default=None, max_length=120),
    installable_only: bool = False,
) -> list[ConnectorDefinitionOut]:
    """List the connector catalogue.

    ``is_installable`` reflects whether a working implementation exists.  A
    catalogue entry with ``is_installable=false`` is a planned/scaffolded
    integration, not a usable connector.
    """
    definitions = registry.list_definitions(
        category=category, search=search, installable_only=installable_only
    )
    return [
        ConnectorDefinitionOut(
            **d.model_dump(),
            is_installable=registry.is_installable(d.connector_id),
        )
        for d in definitions
    ]


@router.get("/categories", response_model=list[str])
def list_categories(principal: CurrentPrincipal) -> list[str]:
    return [c.value for c in ConnectorCategory]


@router.get("/{connector_id}", response_model=ConnectorDefinitionOut)
def get_connector(connector_id: str, principal: CurrentPrincipal) -> ConnectorDefinitionOut:
    definition = registry.get_definition(connector_id)
    return ConnectorDefinitionOut(
        **definition.model_dump(), is_installable=registry.is_installable(connector_id)
    )
