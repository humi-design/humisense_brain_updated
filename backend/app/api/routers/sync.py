"""Synchronization, dead-letter, outbox and Integration Health Centre endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.api.deps import AdminPrincipal, CurrentPrincipal, DbSession
from app.api.schemas import AuditLogOut, DeadLetterOut, SyncRunOut
from app.db import models
from app.schemas.contracts import SyncMode
from app.services.connection_service import ConnectionService
from app.sync.engine import OutboxPublisher, SyncEngine

router = APIRouter(tags=["sync"])


@router.post("/connections/{connection_id}/sync", response_model=SyncRunOut)
async def run_sync(
    connection_id: str,
    principal: AdminPrincipal,
    db: DbSession,
    resource_id: str | None = Query(default=None),
    mode: SyncMode | None = Query(default=None),
) -> SyncRunOut:
    """Run a synchronisation. A failure is returned as a visible, recoverable error."""
    engine = SyncEngine(db)
    run = await engine.run(
        principal.tenant_id, connection_id, resource_id=resource_id, mode=mode,
        actor_id=principal.user_id,
    )
    return SyncRunOut(
        run_id=run.id,
        connection_id=run.connection_id,
        resource_id=run.resource_id,
        mode=run.mode,
        status=run.status,
        records_fetched=run.records_fetched,
        records_written=run.records_written,
        records_skipped=run.records_skipped,
        error=run.error,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


@router.get("/connections/{connection_id}/sync-runs", response_model=list[SyncRunOut])
def list_sync_runs(
    connection_id: str, principal: CurrentPrincipal, db: DbSession, limit: int = Query(default=50, le=200)
) -> list[SyncRunOut]:
    ConnectionService(db).get_connection(principal.tenant_id, connection_id)
    rows = db.execute(
        select(models.SyncRunRow)
        .where(
            models.SyncRunRow.connection_id == connection_id,
            models.SyncRunRow.tenant_id == principal.tenant_id,
        )
        .order_by(models.SyncRunRow.started_at.desc())
        .limit(limit)
    ).scalars().all()
    return [
        SyncRunOut(
            run_id=row.id,
            connection_id=row.connection_id,
            resource_id=row.resource_id,
            mode=row.mode,
            status=row.status,
            records_fetched=row.records_fetched,
            records_written=row.records_written,
            records_skipped=row.records_skipped,
            error=row.error,
            started_at=row.started_at,
            finished_at=row.finished_at,
        )
        for row in rows
    ]


@router.get("/dead-letters", response_model=list[DeadLetterOut])
def list_dead_letters(
    principal: CurrentPrincipal,
    db: DbSession,
    connection_id: str | None = Query(default=None),
) -> list[DeadLetterOut]:
    engine = SyncEngine(db)
    return [
        DeadLetterOut(
            id=row.id,
            connection_id=row.connection_id,
            resource_id=row.resource_id,
            reason=row.reason,
            payload=row.payload,
            resolved=row.resolved,
            created_at=row.created_at,
        )
        for row in engine.list_dead_letters(principal.tenant_id, connection_id)
    ]


@router.post("/dead-letters/{dead_letter_id}/resolve", response_model=DeadLetterOut)
def resolve_dead_letter(
    dead_letter_id: str, principal: AdminPrincipal, db: DbSession
) -> DeadLetterOut:
    row = SyncEngine(db).resolve_dead_letter(principal.tenant_id, dead_letter_id)
    return DeadLetterOut(
        id=row.id,
        connection_id=row.connection_id,
        resource_id=row.resource_id,
        reason=row.reason,
        payload=row.payload,
        resolved=row.resolved,
        created_at=row.created_at,
    )


@router.get("/audit-logs", response_model=list[AuditLogOut])
def list_audit_logs(
    principal: CurrentPrincipal,
    db: DbSession,
    action: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
) -> list[AuditLogOut]:
    stmt = (
        select(models.AuditLog)
        .where(models.AuditLog.tenant_id == principal.tenant_id)
        .order_by(models.AuditLog.created_at.desc())
        .limit(limit)
    )
    if action:
        stmt = stmt.where(models.AuditLog.action == action)
    rows = db.execute(stmt).scalars().all()
    return [
        AuditLogOut(
            id=row.id,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            actor_id=row.actor_id,
            detail=row.detail or {},
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/outbox")
def list_outbox(
    principal: CurrentPrincipal, db: DbSession, limit: int = Query(default=50, le=200)
) -> list[dict]:
    """Inspect queued Layer 2 events. Payloads are tenant-scoped."""
    rows = db.execute(
        select(models.EventOutbox)
        .where(models.EventOutbox.tenant_id == principal.tenant_id)
        .order_by(models.EventOutbox.created_at.desc())
        .limit(limit)
    ).scalars().all()
    return [
        {
            "event_id": row.id,
            "event_type": row.event_type,
            "schema_version": row.schema_version,
            "connection_id": row.connection_id,
            "idempotency_key": row.idempotency_key,
            "published": row.published,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.post("/outbox/drain")
async def drain_outbox(
    principal: AdminPrincipal, db: DbSession, limit: int = Query(default=100, le=1000)
) -> dict:
    """Publish queued events to Layer 2 (no-op until a transport is configured)."""
    publisher = OutboxPublisher(db, transport=None)
    published = await publisher.publish_pending(principal.tenant_id, limit)
    return {"published": published, "pending": len(publisher.pending(principal.tenant_id, limit))}
