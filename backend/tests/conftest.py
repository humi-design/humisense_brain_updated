"""Shared test fixtures.

The test suite uses SQLite (in-memory) and an injectable HTTP transport so
connector logic is exercised without network access.  Everything that is
mocked is labelled ``MOCK`` in the test name or body so no mocked result is
mistaken for a verified provider integration.
"""

from __future__ import annotations

import os
import uuid

import pytest

os.environ.setdefault("HUMISENSE_ENVIRONMENT", "test")
os.environ.setdefault("HUMISENSE_DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("HUMISENSE_CREDENTIAL_ENCRYPTION_KEY", "0" * 64)

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.connectors.bootstrap import bootstrap_registry  # noqa: E402
from app.connectors.registry import registry  # noqa: E402
from app.db import models  # noqa: E402
from app.db.session import get_engine, get_session_factory, reset_engine  # noqa: E402

bootstrap_registry(registry)


@pytest.fixture(autouse=True)
def _fresh_database():
    reset_engine()
    from app.db.models import Base

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    reset_engine()


@pytest.fixture
def db():
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture
def tenant(db) -> models.Tenant:
    from app.connectors.bootstrap import persist_registry

    persist_registry(db)
    row = models.Tenant(id=str(uuid.uuid4()), name="Acme Manufacturing", slug="acme")
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def other_tenant(db) -> models.Tenant:
    row = models.Tenant(id=str(uuid.uuid4()), name="Globex", slug="globex")
    db.add(row)
    db.commit()
    return row


class FakeTransport:
    """Deterministic HTTP transport for connector tests (MOCK).

    ``routes`` maps ``(method, path)`` to a callable returning
    ``(status_code, json_body, headers)``.
    """

    def __init__(self, routes: dict | None = None):
        self.routes = routes or {}
        self.requests: list[dict] = []

    def handle(self, method: str, url: str, **kwargs):
        self.requests.append({"method": method, "url": url, **kwargs})
        from urllib.parse import urlsplit

        path = urlsplit(url).path
        handler = self.routes.get((method.upper(), path)) or self.routes.get(("*", path))
        if handler is None:
            return _FakeResponse(404, {"error": "not_found"})
        result = handler(**kwargs) if callable(handler) else handler
        if isinstance(result, _FakeResponse):
            return result
        status_code, body, headers = (result + ({},))[:3] if len(result) < 3 else result
        return _FakeResponse(status_code, body, headers)


class _FakeResponse:
    def __init__(self, status_code: int, body, headers: dict | None = None):
        import json

        self.status_code = status_code
        self._body = body
        self.headers = dict(headers or {})
        self.text = json.dumps(body) if not isinstance(body, (str, bytes)) else str(body)
        self.content = self.text.encode()

    def json(self):
        return self._body

    @property
    def is_redirect(self) -> bool:
        return self.status_code in {301, 302, 303, 307, 308}


@pytest.fixture
def fake_transport() -> FakeTransport:
    return FakeTransport()
