"""Synchronization engine.

Responsibilities
----------------
* Initial full sync, incremental sync (cursor + watermark) and webhook-triggered sync.
* Durable checkpoints so a failed run resumes from the last good cursor.
* Bounded retries with exponential backoff and jitter; a run that exhausts
  retries fails *visibly* and its checkpoint is preserved for recovery.
* Duplicate detection via a content hash and a per-record idempotency key.
* Dead-letter capture for records that cannot be processed.
* Publishes :class:`EventEnvelope` records into the transactional outbox for
  Layer 2.  Layer 1 never interprets business meaning.

Layer boundary: this module moves and guarantees data.  It does not extract
tasks, prioritise work or reason about content.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.registry import registry
from app.core.config import settings
from app.core.errors import (
    ConnectorError,
    ConnectorRateLimited,
    ConnectorTransientError,
    NotFoundError,
)
from app.core.logging import get_logger
from app.db import models
from app.schemas.contracts import (
    AuditAction,
    EventEnvelope,
    NormalizedRecord,
    SyncMode,
    SyncRunStatus,
)

logger = get_logger(__name__)

EVENT_RECORD_OBSERVED = "connector.record.observed"
EVENT_SYNC_COMPLETED = "connector.sync.completed"
EVENT_SYNC_FAILED = "connector.sync.failed"
EVENT_CONNECTION_HEALTH = "connector.connection.health"


def content_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class SyncEngine:
    def __init__(self, session: Session) -> None:
        self.session = session

    # -- checkpoint helpers ---------------------------------------------

    def _get_checkpoint(self, connection_id: str, resource_id: str) -> models.SyncCheckpointRow:
        row = self.session.execute(
            select(models.SyncCheckpointRow).where(
                models.SyncCheckpointRow.connection_id == connection_id,
                models.SyncCheckpointRow.resource_id == resource_id,
            )
        ).scalar_one_or_none()
        if row is None:
            row = models.SyncCheckpointRow(
                id=str(uuid.uuid4()),
                tenant_id=self._tenant_id,
                connection_id=connection_id,
                resource_id=resource_id,
            )
            self.session.add(row)
            self.session.flush()
        return row

    # -- event publishing -------------------------------------------------

    def _publish(
        self,
        *,
        tenant_id: str,
        connection: models.Connection,
        event_type: str,
        payload: dict[str, Any],
        idempotency_key: str,
        resource_id: str | None = None,
    ) -> None:
        envelope = EventEnvelope(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            tenant_id=tenant_id,
            connection_id=connection.id,
            connector_id=connection.connector_id,
            resource_id=resource_id,
            idempotency_key=idempotency_key,
            payload=payload,
        )
        exists = self.session.execute(
            select(models.EventOutbox.id).where(
                models.EventOutbox.idempotency_key == idempotency_key
            )
        ).scalar_one_or_none()
        if exists is not None:
            return
        self.session.add(
            models.EventOutbox(
                id=envelope.event_id,
                tenant_id=tenant_id,
                connection_id=connection.id,
                event_type=event_type,
                schema_version=envelope.schema_version,
                idempotency_key=idempotency_key,
                payload=envelope.model_dump(mode="json"),
            )
        )

    # -- main entry point -------------------------------------------------

    async def run(
        self,
        tenant_id: str,
        connection_id: str,
        *,
        resource_id: str | None = None,
        mode: SyncMode | None = None,
        actor_id: str | None = None,
    ) -> models.SyncRunRow:
        self._tenant_id = tenant_id
        connection = self._load_connection(tenant_id, connection_id)
        sync_config = connection.sync_config
        effective_mode = mode or SyncMode(sync_config.mode if sync_config else "incremental")

        run = models.SyncRunRow(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            connection_id=connection.id,
            resource_id=resource_id,
            mode=effective_mode.value,
            status=SyncRunStatus.RUNNING.value,
        )
        self.session.add(run)
        connection.status = "synchronizing"
        self._audit(tenant_id, AuditAction.SYNC_STARTED, actor_id, connection.id,
                    {"mode": effective_mode.value, "resource_id": resource_id})
        self.session.flush()

        try:
            targets = self._resolve_targets(connection, resource_id)
            if not targets:
                raise ConnectorError("No resources are selected for synchronization.")
            for target in targets:
                await self._sync_resource(
                    tenant_id, connection, run, target, effective_mode, sync_config
                )
        except Exception as exc:  # noqa: BLE001 - recorded and surfaced
            run.status = SyncRunStatus.FAILED.value
            run.finished_at = datetime.now(timezone.utc)
            run.error = _safe_error(exc)
            connection.status = "degraded"
            connection.last_error = run.error
            connection.consecutive_failures += 1
            self._publish(
                tenant_id=tenant_id,
                connection=connection,
                event_type=EVENT_SYNC_FAILED,
                payload={"run_id": run.id, "error": run.error, "mode": effective_mode.value},
                idempotency_key=f"sync-failed:{run.id}",
                resource_id=resource_id,
            )
            self._audit(tenant_id, AuditAction.SYNC_FAILED, actor_id, connection.id,
                        {"run_id": run.id, "error": run.error})
            # Persist the failure so it is visible after the request rollback.
            self.session.commit()
            raise
        else:
            run.status = SyncRunStatus.SUCCEEDED.value
            run.finished_at = datetime.now(timezone.utc)
            connection.status = "healthy"
            connection.last_successful_sync = run.finished_at
            connection.last_error = None
            connection.consecutive_failures = 0
            self._publish(
                tenant_id=tenant_id,
                connection=connection,
                event_type=EVENT_SYNC_COMPLETED,
                payload={
                    "run_id": run.id,
                    "mode": effective_mode.value,
                    "records_fetched": run.records_fetched,
                    "records_written": run.records_written,
                    "records_skipped": run.records_skipped,
                },
                idempotency_key=f"sync-completed:{run.id}",
                resource_id=resource_id,
            )
            self._audit(tenant_id, AuditAction.SYNC_SUCCEEDED, actor_id, connection.id,
                        {"run_id": run.id, "records_written": run.records_written})
            self.session.flush()
            return run

    def _load_connection(self, tenant_id: str, connection_id: str) -> models.Connection:
        connection = self.session.execute(
            select(models.Connection).where(
                models.Connection.id == connection_id,
                models.Connection.tenant_id == tenant_id,
            )
        ).scalar_one_or_none()
        if connection is None:
            raise NotFoundError("Connection not found.")
        if connection.status == "revoked":
            raise ConnectorError("Connection has been revoked; synchronisation is disabled.")
        return connection

    def _resolve_targets(self, connection: models.Connection, resource_id: str | None) -> list[str]:
        if resource_id:
            return [resource_id]
        selected = [
            row.external_id
            for row in self.session.execute(
                select(models.ConnectionResource).where(
                    models.ConnectionResource.connection_id == connection.id,
                    models.ConnectionResource.is_selected.is_(True),
                )
            ).scalars().all()
        ]
        return selected

    async def _sync_resource(
        self,
        tenant_id: str,
        connection: models.Connection,
        run: models.SyncRunRow,
        resource_id: str,
        mode: SyncMode,
        sync_config: models.SyncConfig | None,
    ) -> None:
        from app.services.connection_service import ConnectionService

        context = ConnectionService(self.session).build_context(tenant_id, connection)
        connector = registry.create(connection.connector_id, context)
        checkpoint = self._get_checkpoint(connection.id, resource_id)

        cursor = checkpoint.cursor
        watermark = checkpoint.watermark
        if mode == SyncMode.FULL:
            cursor = None
            watermark = None

        page_size = sync_config.page_size if sync_config else settings.connector_page_size
        max_pages = settings.connector_max_pages
        max_retries = sync_config.max_retries if sync_config else settings.sync_max_retries
        seen_hashes: set[str] = set()

        pages = 0
        while pages < max_pages:
            page = await self._fetch_with_retry(
                connector, resource_id, mode, cursor, watermark, page_size, max_retries
            )
            pages += 1
            run.records_fetched += len(page.records)

            for record in page.records:
                self._ingest_record(tenant_id, connection, run, resource_id, record, seen_hashes)

            if page.watermark and (watermark is None or page.watermark > watermark):
                watermark = page.watermark
            if page.next_cursor is None:
                checkpoint.cursor = None
                checkpoint.watermark = watermark
                checkpoint.records_seen += len(page.records)
                checkpoint.updated_at = datetime.now(timezone.utc)
                break
            cursor = page.next_cursor
            checkpoint.cursor = cursor
            checkpoint.watermark = watermark
            checkpoint.records_seen += len(page.records)
            checkpoint.updated_at = datetime.now(timezone.utc)
            # Persist progress so a crash resumes from the last good page.
            self.session.flush()
        else:
            raise ConnectorError(
                f"Sync for '{resource_id}' exceeded the maximum of {max_pages} pages."
            )

    async def _fetch_with_retry(
        self,
        connector: Any,
        resource_id: str,
        mode: SyncMode,
        cursor: str | None,
        watermark: Any,
        page_size: int,
        max_retries: int,
    ):
        attempt = 0
        while True:
            try:
                if mode == SyncMode.FULL or watermark is None:
                    return await connector.fetch_records(
                        resource_id, cursor=cursor, page_size=page_size
                    )
                return await connector.fetch_incremental_records(
                    resource_id, cursor=cursor, watermark=watermark, page_size=page_size
                )
            except ConnectorRateLimited as exc:
                if attempt >= max_retries:
                    raise
                delay = exc.retry_after or _backoff(attempt)
                await asyncio.sleep(delay)
            except ConnectorTransientError:
                if attempt >= max_retries:
                    raise
                await asyncio.sleep(_backoff(attempt))
            attempt += 1

    def _ingest_record(
        self,
        tenant_id: str,
        connection: models.Connection,
        run: models.SyncRunRow,
        resource_id: str,
        record: NormalizedRecord,
        seen_hashes: set[str],
    ) -> None:
        digest = content_hash(record.payload)
        record.content_hash = digest
        if digest in seen_hashes:
            run.records_skipped += 1
            return
        seen_hashes.add(digest)

        idempotency_key = (
            f"{connection.id}:{resource_id}:{record.source_record_id}:{digest[:16]}"
        )
        exists = self.session.execute(
            select(models.EventOutbox.id).where(
                models.EventOutbox.idempotency_key == idempotency_key
            )
        ).scalar_one_or_none()
        if exists is not None:
            run.records_skipped += 1
            return

        self._publish(
            tenant_id=tenant_id,
            connection=connection,
            event_type=EVENT_RECORD_OBSERVED,
            payload=record.model_dump(mode="json"),
            idempotency_key=idempotency_key,
            resource_id=resource_id,
        )
        run.records_written += 1

    def _audit(
        self,
        tenant_id: str,
        action: AuditAction,
        actor_id: str | None,
        connection_id: str,
        detail: dict[str, Any],
    ) -> None:
        self.session.add(
            models.AuditLog(
                tenant_id=tenant_id,
                actor_id=actor_id,
                action=action.value,
                resource_type="connection",
                resource_id=connection_id,
                detail=detail,
            )
        )

    # -- dead letter ------------------------------------------------------

    def record_dead_letter(
        self,
        tenant_id: str,
        connection_id: str,
        *,
        reason: str,
        payload: dict[str, Any],
        sync_run_id: str | None = None,
        resource_id: str | None = None,
    ) -> models.DeadLetterRow:
        row = models.DeadLetterRow(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            connection_id=connection_id,
            sync_run_id=sync_run_id,
            resource_id=resource_id,
            reason=reason,
            payload=payload,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def list_dead_letters(self, tenant_id: str, connection_id: str | None = None):
        stmt = select(models.DeadLetterRow).where(models.DeadLetterRow.tenant_id == tenant_id)
        if connection_id:
            stmt = stmt.where(models.DeadLetterRow.connection_id == connection_id)
        return list(self.session.execute(stmt.order_by(models.DeadLetterRow.created_at.desc())).scalars())

    def resolve_dead_letter(self, tenant_id: str, dead_letter_id: str) -> models.DeadLetterRow:
        row = self.session.execute(
            select(models.DeadLetterRow).where(
                models.DeadLetterRow.id == dead_letter_id,
                models.DeadLetterRow.tenant_id == tenant_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError("Dead letter not found.")
        row.resolved = True
        self.session.flush()
        return row


def _backoff(attempt: int) -> float:
    base = settings.sync_backoff_base_seconds * (2 ** attempt)
    jitter = random.uniform(0, base * 0.25)
    return min(base + jitter, settings.sync_backoff_max_seconds)


def _safe_error(exc: Exception) -> str:
    from app.core.logging import redact_text

    message = getattr(exc, "message", None) or str(exc) or type(exc).__name__
    return redact_text(message)[:1000]


class OutboxPublisher:
    """Drains the outbox and hands events to Layer 2.

    The transport is injectable: production wires an HTTP/Kafka/queue client,
    tests use an in-memory collector.  Until a transport is configured events
    remain durably queued - nothing is lost.
    """

    def __init__(self, session: Session, transport: Any | None = None) -> None:
        self.session = session
        self.transport = transport

    def pending(self, tenant_id: str | None = None, limit: int = 100) -> list[models.EventOutbox]:
        stmt = (
            select(models.EventOutbox)
            .where(models.EventOutbox.published.is_(False))
            .order_by(models.EventOutbox.created_at)
            .limit(limit)
        )
        if tenant_id:
            stmt = stmt.where(models.EventOutbox.tenant_id == tenant_id)
        return list(self.session.execute(stmt).scalars().all())

    async def publish_pending(self, tenant_id: str | None = None, limit: int = 100) -> int:
        if self.transport is None:
            return 0
        published = 0
        for event in self.pending(tenant_id, limit):
            envelope = EventEnvelope(**event.payload)
            try:
                await self.transport(envelope)
            except Exception as exc:  # noqa: BLE001 - leave queued for retry
                logger.warning("outbox_publish_failed", event_id=event.id,
                               error=type(exc).__name__)
                continue
            event.published = True
            event.published_at = datetime.now(timezone.utc)
            published += 1
        self.session.flush()
        return published
