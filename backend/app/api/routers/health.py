"""Health, metrics and event-contract endpoints."""

from __future__ import annotations

import time

from fastapi import APIRouter, Response
from sqlalchemy import text

from app.api.deps import CurrentPrincipal, DbSession
from app.api.schemas import EventContractOut, HealthOut
from app.connectors.registry import registry
from app.core.config import settings
from app.db.session import get_engine
from app.events.contract import contract_document

router = APIRouter(tags=["health"])

VERSION = "0.1.0"

# Minimal in-process counters.  Replace with a Prometheus client when a
# metrics backend is provisioned.
_METRICS: dict[str, float] = {
    "requests_total": 0,
    "connector_tests_total": 0,
    "sync_runs_total": 0,
    "sync_failures_total": 0,
    "webhook_rejected_total": 0,
    "egress_blocked_total": 0,
}


def increment(metric: str, amount: float = 1.0) -> None:
    _METRICS[metric] = _METRICS.get(metric, 0.0) + amount


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    db_status = "ok"
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_status = "unavailable"
    definitions = registry.list_definitions()
    return HealthOut(
        status="ok" if db_status == "ok" else "degraded",
        version=VERSION,
        database=db_status,
        connectors_registered=len(definitions),
        connectors_installable=len(registry.list_definitions(installable_only=True)),
    )


@router.get("/metrics")
def metrics() -> Response:
    lines = [f"humisense_layer1_{key} {value}" for key, value in sorted(_METRICS.items())]
    lines.append(f"humisense_layer1_up 1")
    return Response("\n".join(lines) + "\n", media_type="text/plain")


@router.get("/events/contract", response_model=EventContractOut)
def event_contract(principal: CurrentPrincipal) -> EventContractOut:
    """The documented Layer 1 -> Layer 2 event contract."""
    document = contract_document()
    return EventContractOut(
        schema_version=document["schema_version"],
        event_types=document["event_types"],
        delivery=document["delivery"],
    )


@router.get("/config/public")
def public_config(principal: CurrentPrincipal) -> dict:
    """Non-secret configuration the frontend needs to render truthfully."""
    return {
        "environment": settings.environment,
        "egress_allow_private": settings.egress_allow_private,
        "egress_allowed_hosts": settings.egress_allowed_hosts,
        "webhook_signature_tolerance_seconds": settings.webhook_signature_tolerance_seconds,
    }
