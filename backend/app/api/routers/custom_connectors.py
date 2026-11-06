"""Universal Connector Studio endpoints (custom connector framework)."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import AdminPrincipal, CurrentPrincipal, DbSession
from app.api.schemas import CustomDefinitionIn, CustomDefinitionOut, TransitionIn
from app.core.errors import NotFoundError
from app.schemas.contracts import AdapterKind, ValidationResult
from app.services.custom_connector_service import CustomConnectorService

router = APIRouter(prefix="/custom-connectors", tags=["custom-connectors"])


def _to_out(row) -> CustomDefinitionOut:  # noqa: ANN001
    return CustomDefinitionOut(
        id=row.id,
        name=row.name,
        adapter_kind=row.adapter_kind,
        version=row.version,
        definition=row.definition,
        review_status=row.review_status,
        validation_report=row.validation_report,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=list[CustomDefinitionOut])
def list_definitions(principal: CurrentPrincipal, db: DbSession) -> list[CustomDefinitionOut]:
    return [_to_out(row) for row in CustomConnectorService(db).list_definitions(principal.tenant_id)]


@router.post("/validate", response_model=ValidationResult)
def validate_definition(payload: CustomDefinitionIn, principal: CurrentPrincipal) -> ValidationResult:
    """Validate a definition without persisting it. Used by the Studio tester."""
    service = CustomConnectorService.__new__(CustomConnectorService)
    return CustomConnectorService.validate(service, payload.adapter_kind, payload.definition)


@router.post("", response_model=CustomDefinitionOut, status_code=status.HTTP_201_CREATED)
def create_definition(
    payload: CustomDefinitionIn, principal: AdminPrincipal, db: DbSession
) -> CustomDefinitionOut:
    row = CustomConnectorService(db).create_definition(
        principal.tenant_id,
        name=payload.name,
        adapter_kind=payload.adapter_kind,
        definition=payload.definition,
        created_by=principal.user_id,
        generated_by_ai=payload.generated_by_ai,
    )
    return _to_out(row)


@router.patch("/{definition_id}", response_model=CustomDefinitionOut)
def update_definition(
    definition_id: str, payload: CustomDefinitionIn, principal: AdminPrincipal, db: DbSession
) -> CustomDefinitionOut:
    row = CustomConnectorService(db).update_definition(
        principal.tenant_id, definition_id, payload.definition
    )
    return _to_out(row)


@router.post("/{definition_id}/transition", response_model=CustomDefinitionOut)
def transition_definition(
    definition_id: str, payload: TransitionIn, principal: AdminPrincipal, db: DbSession
) -> CustomDefinitionOut:
    """Move a definition through draft -> pending_review -> approved -> published."""
    row = CustomConnectorService(db).transition(
        principal.tenant_id, definition_id, payload.target, actor_id=principal.user_id
    )
    return _to_out(row)


@router.get("/adapter-kinds", response_model=list[str])
def adapter_kinds(principal: CurrentPrincipal) -> list[str]:
    return [k.value for k in AdapterKind]
