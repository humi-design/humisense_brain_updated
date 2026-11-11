"""FastAPI application factory for Humisense Brain - Layer 1."""

from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers import (
    connections,
    connectors,
    custom_connectors,
    discovery,
    health as health_router,
    sync,
    tenants,
    webhooks,
)
from app.connectors.bootstrap import bootstrap_registry, persist_registry
from app.connectors.registry import registry
from app.core.config import settings
from app.core.errors import HumisenseError
from app.core.logging import configure_logging, get_logger
from app.db.session import get_session_factory

configure_logging("DEBUG" if settings.debug else "INFO", json_output=not settings.debug)
logger = get_logger(__name__)


def _sync_connector_registry() -> None:
    """Refresh the durable connector registry table from the in-process catalogue.

    The registry table is a projection of the code-defined catalogue, so it is
    rewritten on every startup. A failure here must not stop the API from
    serving: the in-process registry is still authoritative for behaviour.
    """
    session = get_session_factory()()
    try:
        count = persist_registry(session)
        session.commit()
        logger.info("connector_registry_synced", connectors=count)
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.warning("connector_registry_sync_failed", error=type(exc).__name__)
    finally:
        session.close()


def create_app() -> FastAPI:
    bootstrap_registry(registry)
    _sync_connector_registry()

    app = FastAPI(
        title="Humisense Brain - Layer 1 Connector & Sensory Platform",
        version="0.1.0",
        description=(
            "Layer 1 owns application connectivity, authentication, connector "
            "configuration, data access, synchronisation, connector health, "
            "technology discovery, universal adapters, the connector registry "
            "and integration administration. Business interpretation belongs to "
            "later layers."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _observability(request: Request, call_next):  # noqa: ANN001
        request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
        started = time.perf_counter()
        health_router.increment("requests_total")
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-Id"] = request_id
        logger.info(
            "request",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(duration_ms, 2),
        )
        return response

    @app.exception_handler(HumisenseError)
    async def _domain_error(_request: Request, exc: HumisenseError) -> JSONResponse:
        payload: dict = {"error": exc.code, "message": exc.message}
        if exc.detail:
            payload["detail"] = exc.detail
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(Exception)
    async def _unhandled(_request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled_error", error=type(exc).__name__)
        return JSONResponse(
            status_code=500, content={"error": "internal_error", "message": "An unexpected error occurred."}
        )

    prefix = settings.api_prefix
    app.include_router(health_router.router, prefix=prefix)
    app.include_router(tenants.router, prefix=prefix)
    app.include_router(connectors.router, prefix=prefix)
    app.include_router(connections.router, prefix=prefix)
    app.include_router(discovery.router, prefix=prefix)
    app.include_router(custom_connectors.router, prefix=prefix)
    app.include_router(sync.router, prefix=prefix)
    app.include_router(webhooks.router, prefix=prefix)
    return app


app = create_app()
