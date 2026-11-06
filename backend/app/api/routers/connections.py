"""Connection management endpoints (the Connection Wizard backend)."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import AdminPrincipal, CurrentPrincipal, DbSession
from app.api.schemas import (
    ConnectionCreateIn,
    ConnectionOut,
    ConnectionResourceOut,
    CredentialRotateIn,
    ResourceSelectionIn,
    SyncConfigureIn,
    TestConnectionOut,
)
from app.core.errors import NotFoundError
from app.db import models
from app.schemas.contracts import ConnectionConfiguration
from app.services.connection_service import ConnectionService

router = APIRouter(prefix="/connections", tags=["connections"])


def _to_out(service: ConnectionService, tenant_id: str, connection: models.Connection) -> ConnectionOut:
    reference = service.credential_reference(tenant_id, connection.id)
    return ConnectionOut(
        connection_id=connection.id,
        connector_id=connection.connector_id,
        provider=connection.provider,
        display_name=connection.display_name,
        account_identifier=connection.account_identifier,
        status=connection.status,
        health_status=connection.health_status,
        health_checked_at=connection.health_checked_at,
        health_latency_ms=connection.health_latency_ms,
        health_message=connection.health_message,
        granted_scopes=list(connection.granted_scopes or []),
        last_successful_sync=connection.last_successful_sync,
        last_error=connection.last_error,
        credential_reference_id=reference.reference_id if reference else None,
        credential_rotated_at=reference.rotated_at if reference else None,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
    )


@router.get("", response_model=list[ConnectionOut])
def list_connections(principal: CurrentPrincipal, db: DbSession) -> list[ConnectionOut]:
    service = ConnectionService(db)
    return [_to_out(service, principal.tenant_id, c) for c in service.list_connections(principal.tenant_id)]


@router.post("", response_model=ConnectionOut, status_code=status.HTTP_201_CREATED)
def create_connection(
    payload: ConnectionCreateIn, principal: AdminPrincipal, db: DbSession
) -> ConnectionOut:
    service = ConnectionService(db)
    connection = service.create_connection(
        principal.tenant_id,
        connector_id=payload.connector_id,
        display_name=payload.display_name,
        configuration=ConnectionConfiguration(**payload.configuration),
        credentials=payload.credentials,
        actor_id=principal.user_id,
        granted_scopes=payload.granted_scopes,
    )
    return _to_out(service, principal.tenant_id, connection)


@router.get("/{connection_id}", response_model=ConnectionOut)
def get_connection(connection_id: str, principal: CurrentPrincipal, db: DbSession) -> ConnectionOut:
    service = ConnectionService(db)
    connection = service.get_connection(principal.tenant_id, connection_id)
    return _to_out(service, principal.tenant_id, connection)


@router.post("/{connection_id}/credentials", response_model=ConnectionOut)
def rotate_credentials(
    connection_id: str, payload: CredentialRotateIn, principal: AdminPrincipal, db: DbSession
) -> ConnectionOut:
    service = ConnectionService(db)
    service.rotate_credentials(
        principal.tenant_id, connection_id, payload.credentials, actor_id=principal.user_id
    )
    connection = service.get_connection(principal.tenant_id, connection_id)
    return _to_out(service, principal.tenant_id, connection)


@router.post("/{connection_id}/test", response_model=TestConnectionOut)
async def test_connection(
    connection_id: str, principal: AdminPrincipal, db: DbSession
) -> TestConnectionOut:
    service = ConnectionService(db)
    result = await service.test_connection(
        principal.tenant_id, connection_id, actor_id=principal.user_id
    )
    return TestConnectionOut(**result.model_dump())


@router.get("/{connection_id}/resources", response_model=list[ConnectionResourceOut])
async def discover_resources(
    connection_id: str, principal: CurrentPrincipal, db: DbSession
) -> list[ConnectionResourceOut]:
    service = ConnectionService(db)
    await service.discover_resources(principal.tenant_id, connection_id, actor_id=principal.user_id)
    rows = db.query(models.ConnectionResource).filter(
        models.ConnectionResource.connection_id == connection_id,
        models.ConnectionResource.tenant_id == principal.tenant_id,
    ).all()
    return [
        ConnectionResourceOut(
            id=row.id,
            external_id=row.external_id,
            name=row.name,
            resource_type=row.resource_type,
            parent_id=row.parent_id,
            is_selected=row.is_selected,
            read_only=row.read_only,
            metadata=row.metadata_json or {},
        )
        for row in rows
    ]


@router.put("/{connection_id}/resources", response_model=list[ConnectionResourceOut])
def select_resources(
    connection_id: str, payload: ResourceSelectionIn, principal: AdminPrincipal, db: DbSession
) -> list[ConnectionResourceOut]:
    service = ConnectionService(db)
    rows = service.select_resources(
        principal.tenant_id, connection_id, payload.external_ids, actor_id=principal.user_id
    )
    return [
        ConnectionResourceOut(
            id=row.id,
            external_id=row.external_id,
            name=row.name,
            resource_type=row.resource_type,
            parent_id=row.parent_id,
            is_selected=row.is_selected,
            read_only=row.read_only,
            metadata=row.metadata_json or {},
        )
        for row in rows
    ]


@router.post("/{connection_id}/sync-config", response_model=dict)
def configure_sync(
    connection_id: str, payload: SyncConfigureIn, principal: AdminPrincipal, db: DbSession
) -> dict:
    service = ConnectionService(db)
    row = service.configure_sync(
        principal.tenant_id, connection_id, payload.to_contract(), actor_id=principal.user_id
    )
    return {
        "connection_id": connection_id,
        "mode": row.mode,
        "schedule_cron": row.schedule_cron,
        "page_size": row.page_size,
        "enabled": row.enabled,
        "write_enabled": row.write_enabled,
    }


@router.post("/{connection_id}/revoke", response_model=ConnectionOut)
def revoke_connection(
    connection_id: str, principal: AdminPrincipal, db: DbSession
) -> ConnectionOut:
    service = ConnectionService(db)
    connection = service.revoke(principal.tenant_id, connection_id, actor_id=principal.user_id)
    return _to_out(service, principal.tenant_id, connection)


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(connection_id: str, principal: AdminPrincipal, db: DbSession) -> None:
    service = ConnectionService(db)
    try:
        service.delete(principal.tenant_id, connection_id, actor_id=principal.user_id)
    except NotFoundError:
        raise
