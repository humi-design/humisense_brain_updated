"""Layer 1 -> Layer 2 event contract.

Layer 1 publishes *raw, provenance-preserving* records.  It does not extract
tasks, prioritise work, build memory or reason about content - those are
Layer 2 responsibilities.  This module is the single, documented definition of
the contract so both layers can rely on it.

Delivery
--------
Events are written to a transactional outbox in the same database transaction
as the sync that produced them, then drained by :class:`OutboxPublisher`.  This
gives at-least-once delivery: a crash between commit and publish leaves the
event queued rather than lost.  Consumers must deduplicate on
``idempotency_key``.
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "1.0"

EVENT_TYPES: list[dict[str, Any]] = [
    {
        "event_type": "connector.record.observed",
        "description": "A source record was retrieved and normalised. Raw payload preserved.",
        "payload": {
            "source_record_id": "string",
            "resource_id": "string",
            "source_metadata": "object",
            "payload": "object",
            "observed_at": "iso8601",
            "source_updated_at": "iso8601|null",
            "content_hash": "sha256",
        },
    },
    {
        "event_type": "connector.sync.completed",
        "description": "A sync run finished successfully for a connection.",
        "payload": {
            "run_id": "string",
            "mode": "full|incremental|webhook",
            "records_fetched": "integer",
            "records_written": "integer",
            "records_skipped": "integer",
        },
    },
    {
        "event_type": "connector.sync.failed",
        "description": "A sync run failed. Checkpoint is preserved for recovery.",
        "payload": {"run_id": "string", "error": "string", "mode": "string"},
    },
    {
        "event_type": "connector.connection.health",
        "description": "Connection health changed (healthy/degraded/unhealthy).",
        "payload": {"status": "string", "latency_ms": "number|null", "message": "string|null"},
    },
]

DELIVERY: dict[str, Any] = {
    "transport": "transactional_outbox",
    "semantics": "at-least-once",
    "deduplication": "idempotency_key",
    "ordering": "per-connection FIFO by created_at",
    "schema_version": SCHEMA_VERSION,
    "tenant_isolation": "Every envelope carries tenant_id; consumers must scope by tenant.",
}


def contract_document() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "event_types": EVENT_TYPES,
        "delivery": DELIVERY,
    }
