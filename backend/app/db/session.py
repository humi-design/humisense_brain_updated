"""Database engine, session factory and PostgreSQL row-level-security helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        connect_args = {}
        kwargs: dict = {}
        if settings.database_url.startswith("sqlite"):
            connect_args = {"check_same_thread": False}
            if ":memory:" in settings.database_url:
                # In-memory SQLite must share a single connection across the
                # whole process, otherwise each session sees an empty database.
                from sqlalchemy.pool import StaticPool

                kwargs["poolclass"] = StaticPool
        _engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            future=True,
            connect_args=connect_args,
            **kwargs,
        )
        if settings.database_url.startswith("sqlite"):
            _enable_sqlite_foreign_keys(_engine)
    return _engine


def _enable_sqlite_foreign_keys(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection, _record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def is_postgres() -> bool:
    return get_engine().dialect.name == "postgresql"


def apply_row_level_security() -> None:
    """Enable PostgreSQL RLS on tenant-owned tables.

    Two roles are assumed: the owner role that runs migrations and a runtime
    role (``humisense_app``) that serves traffic.  RLS forces every query to
    carry the current tenant, so a missing ``WHERE tenant_id`` becomes an
    empty result rather than a cross-tenant leak.

    This is a no-op on SQLite (used in tests), where tenant scoping is enforced
    in the service layer.

    WARNING — not safe to enable yet.  The policies read
    ``current_setting('humisense.current_tenant')``, but the request path
    (``app.api.deps.get_db``) never sets it.  With ``FORCE ROW LEVEL SECURITY``
    in place every query would therefore see zero rows, and provisioning could
    not insert the first tenant.  Calling this before the request path binds
    the GUC takes the application offline.  It is retained as the basis for
    that work, and is not invoked at startup.
    """
    if not is_postgres():
        return
    tenant_tables = [
        "connections",
        "credentials",
        "connection_resources",
        "sync_configs",
        "sync_checkpoints",
        "sync_runs",
        "dead_letters",
        "event_outbox",
        "integration_assessments",
        "custom_connector_definitions",
        "audit_logs",
        "webhook_deliveries",
        "users",
    ]
    with get_engine().begin() as conn:
        for table in tenant_tables:
            conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
            conn.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
            conn.execute(text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
            conn.execute(
                text(
                    f"CREATE POLICY tenant_isolation ON {table} "
                    "USING (tenant_id = current_setting('humisense.current_tenant', true)) "
                    "WITH CHECK (tenant_id = current_setting('humisense.current_tenant', true))"
                )
            )


@contextmanager
def tenant_session(tenant_id: str) -> Iterator[Session]:
    """Yield a session whose PostgreSQL connection is bound to ``tenant_id``."""
    session = get_session_factory()()
    try:
        if is_postgres():
            session.execute(
                text("SELECT set_config('humisense.current_tenant', :tid, false)"),
                {"tid": tenant_id},
            )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine() -> None:
    """Test helper: drop the cached engine so a new URL takes effect."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
