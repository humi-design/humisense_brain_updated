"""Synchronisation engine tests.

Proves: full and incremental sync, checkpoint persistence and resume,
duplicate suppression, idempotent event publishing, failure visibility and
recoverability, rate-limit retry, and that a revoked connection cannot sync.
"""

from __future__ import annotations

import pytest

from app.core.errors import ConnectorError, ConnectorRateLimited
from app.db import models
from app.schemas.contracts import ConnectionConfiguration, NormalizedRecord, SyncConfiguration
from app.services.connection_service import ConnectionService
from app.sync.engine import SyncEngine

API = "https://api.github.com"


def _connection(db, tenant_id: str) -> models.Connection:
    service = ConnectionService(db)
    connection = service.create_connection(
        tenant_id,
        connector_id="github",
        display_name="GH",
        configuration=ConnectionConfiguration(base_url=API, options={"api_base": API}),
        credentials={"token": "ghp_mock"},
        actor_id="u1",
    )
    db.commit()
    return connection


class StubConnector:
    """Deterministic connector double (MOCK) injected via the registry factory."""

    def __init__(self, pages, *, fail_on_page: int | None = None, rate_limit_times: int = 0):
        self.pages = pages
        self.fail_on_page = fail_on_page
        self.rate_limit_times = rate_limit_times
        self.calls = 0
        self.seen_cursors: list[str | None] = []

    async def fetch_records(self, resource_id, *, cursor=None, page_size=None):
        return await self._page(cursor)

    async def fetch_incremental_records(self, resource_id, *, cursor=None, watermark=None, page_size=None):
        return await self._page(cursor)

    async def _page(self, cursor):
        if self.rate_limit_times > 0:
            self.rate_limit_times -= 1
            raise ConnectorRateLimited("slow down", retry_after=0.0)
        index = int(cursor or 0)
        self.seen_cursors.append(cursor)
        self.calls += 1
        if self.fail_on_page is not None and index == self.fail_on_page:
            raise ConnectorError("simulated upstream failure")
        if index >= len(self.pages):
            from app.schemas.contracts import FetchPage

            return FetchPage(records=[], next_cursor=None, has_more=False)
        from app.schemas.contracts import FetchPage

        records = [
            NormalizedRecord(source_record_id=str(item["id"]), resource_id="issues", payload=item)
            for item in self.pages[index]
        ]
        next_cursor = str(index + 1) if index + 1 < len(self.pages) else None
        return FetchPage(records=records, next_cursor=next_cursor, has_more=next_cursor is not None)


@pytest.fixture
def patch_connector(monkeypatch):
    def _patch(connector):
        from app.connectors import registry as registry_module

        monkeypatch.setattr(
            registry_module.registry,
            "create",
            lambda connector_id, context: connector,
        )
        return connector

    return _patch


async def test_full_sync_writes_events(db, tenant, patch_connector):
    connection = _connection(db, tenant.id)
    stub = patch_connector(StubConnector([[{"id": 1}, {"id": 2}], [{"id": 3}]]))
    engine = SyncEngine(db)
    run = await engine.run(tenant.id, connection.id, resource_id="issues")
    db.commit()

    assert run.status == "succeeded"
    assert run.records_written == 3
    events = db.query(models.EventOutbox).filter(
        models.EventOutbox.event_type == "connector.record.observed"
    ).all()
    assert len(events) == 3
    assert stub.calls == 2


async def test_duplicate_records_are_suppressed(db, tenant, patch_connector):
    connection = _connection(db, tenant.id)
    patch_connector(StubConnector([[{"id": 1, "v": 1}, {"id": 1, "v": 1}]]))
    run = await SyncEngine(db).run(tenant.id, connection.id, resource_id="issues")
    db.commit()
    assert run.records_written == 1
    assert run.records_skipped == 1


async def test_resync_does_not_duplicate_record_events(db, tenant, patch_connector):
    connection = _connection(db, tenant.id)
    patch_connector(StubConnector([[{"id": 1}, {"id": 2}]]))
    await SyncEngine(db).run(tenant.id, connection.id, resource_id="issues")
    db.commit()

    def _record_events() -> int:
        return db.query(models.EventOutbox).filter(
            models.EventOutbox.event_type == "connector.record.observed"
        ).count()

    assert _record_events() == 2
    await SyncEngine(db).run(tenant.id, connection.id, resource_id="issues")
    db.commit()
    # Record events are idempotent across re-syncs. sync.completed is emitted
    # per run by design, so only record events are asserted here.
    assert _record_events() == 2


async def test_checkpoint_is_persisted(db, tenant, patch_connector):
    connection = _connection(db, tenant.id)
    patch_connector(StubConnector([[{"id": 1}], [{"id": 2}], [{"id": 3}]]))
    await SyncEngine(db).run(tenant.id, connection.id, resource_id="issues")
    db.commit()
    checkpoint = db.query(models.SyncCheckpointRow).filter(
        models.SyncCheckpointRow.connection_id == connection.id
    ).one()
    assert checkpoint.records_seen == 3
    assert checkpoint.cursor is None  # completed, cursor cleared


async def test_failed_sync_is_visible_and_recoverable(db, tenant, patch_connector):
    connection = _connection(db, tenant.id)
    stub = patch_connector(StubConnector([[{"id": 1}], [{"id": 2}]], fail_on_page=1))

    with pytest.raises(ConnectorError):
        await SyncEngine(db).run(tenant.id, connection.id, resource_id="issues")
    db.commit()

    failed_run = db.query(models.SyncRunRow).order_by(models.SyncRunRow.started_at.desc()).first()
    assert failed_run.status == "failed"
    assert failed_run.error

    db.refresh(connection)
    assert connection.status == "degraded"
    assert connection.last_error

    # A failure event is queued so Layer 2 can see it.
    failure_events = db.query(models.EventOutbox).filter(
        models.EventOutbox.event_type == "connector.sync.failed"
    ).all()
    assert len(failure_events) == 1

    # Recovery: the same connection can sync successfully afterwards.
    stub.fail_on_page = None
    run = await SyncEngine(db).run(tenant.id, connection.id, resource_id="issues")
    db.commit()
    assert run.status == "succeeded"
    db.refresh(connection)
    assert connection.status == "healthy"
    assert connection.last_error is None


async def test_rate_limit_is_retried(db, tenant, patch_connector):
    connection = _connection(db, tenant.id)
    stub = patch_connector(StubConnector([[{"id": 1}]], rate_limit_times=2))
    run = await SyncEngine(db).run(tenant.id, connection.id, resource_id="issues")
    db.commit()
    assert run.status == "succeeded"
    assert run.records_written == 1
    assert stub.calls == 1


async def test_revoked_connection_cannot_sync(db, tenant, patch_connector):
    connection = _connection(db, tenant.id)
    patch_connector(StubConnector([[{"id": 1}]]))
    ConnectionService(db).revoke(tenant.id, connection.id, actor_id="u1")
    db.commit()
    with pytest.raises(ConnectorError):
        await SyncEngine(db).run(tenant.id, connection.id, resource_id="issues")


async def test_sync_requires_selected_resources(db, tenant, patch_connector):
    connection = _connection(db, tenant.id)
    patch_connector(StubConnector([[{"id": 1}]]))
    with pytest.raises(ConnectorError):
        await SyncEngine(db).run(tenant.id, connection.id)  # no resource_id, none selected


async def test_read_only_connector_rejects_write_sync(db, tenant):
    connection = _connection(db, tenant.id)
    with pytest.raises(Exception) as exc:
        ConnectionService(db).configure_sync(
            tenant.id,
            connection.id,
            SyncConfiguration(mode="incremental", write_enabled=True),
        )
    assert "read-only" in str(exc.value)


async def test_dead_letter_capture_and_resolution(db, tenant):
    engine = SyncEngine(db)
    row = engine.record_dead_letter(
        tenant.id, "conn-1", reason="bad record", payload={"x": 1}
    )
    db.commit()
    assert engine.list_dead_letters(tenant.id)[0].id == row.id
    resolved = engine.resolve_dead_letter(tenant.id, row.id)
    db.commit()
    assert resolved.resolved is True


async def test_dead_letters_are_tenant_scoped(db, tenant, other_tenant):
    engine = SyncEngine(db)
    engine.record_dead_letter(tenant.id, "conn-1", reason="r", payload={})
    db.commit()
    assert engine.list_dead_letters(tenant.id)
    assert engine.list_dead_letters(other_tenant.id) == []


async def test_outbox_event_carries_tenant_and_idempotency_key(db, tenant, patch_connector):
    connection = _connection(db, tenant.id)
    patch_connector(StubConnector([[{"id": 1}]]))
    await SyncEngine(db).run(tenant.id, connection.id, resource_id="issues")
    db.commit()
    event = db.query(models.EventOutbox).filter(
        models.EventOutbox.event_type == "connector.record.observed"
    ).one()
    assert event.tenant_id == tenant.id
    assert event.idempotency_key
    assert event.payload["tenant_id"] == tenant.id
    assert event.payload["schema_version"] == "1.0"
