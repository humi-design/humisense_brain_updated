"""Universal adapter tests: REST pagination, SQL read-only enforcement, files."""

from __future__ import annotations

import pytest

from app.connectors.adapters.rest_adapter import RestAdapterConnector
from app.connectors.adapters.sql_adapter import SqlAdapterConnector, validate_read_only_sql
from app.connectors.base import ConnectorContext
from app.core.errors import EgressBlockedError, ValidationError
from app.schemas.contracts import ConnectionConfiguration
from tests.fake_http import FakeHttpClient, FakeResponse, static

# ---------------------------------------------------------------------------
# REST adapter
# ---------------------------------------------------------------------------

REST_DEF = {
    "base_url": "https://api.example.com/v1",
    "auth": {"type": "bearer_token"},
    "resources": [
        {
            "id": "orders",
            "path": "/orders",
            "items_path": "data.items",
            "record_id_path": "id",
            "updated_at_path": "updated_at",
            "incremental_param": "updated_since",
            "page_size": 2,
            "pagination": {
                "strategy": "page",
                "page_param": "page",
                "size_param": "per_page",
                "total_json_path": "data.total",
            },
            "fields": {"order_id": "id", "status": "state"},
        }
    ],
}


def _rest_ctx(client) -> ConnectorContext:
    return ConnectorContext(
        tenant_id="t1",
        connection_id="c1",
        connector_id="universal_rest",
        configuration=ConnectionConfiguration(
            base_url="https://api.example.com/v1", options={"adapter": REST_DEF}
        ),
        credentials={"token": "tok"},
        http_client=client,
    )


def test_rest_configuration_validation():
    ctx = _rest_ctx(FakeHttpClient())
    result = RestAdapterConnector(ctx).validate_configuration(ctx.configuration)
    assert result.valid


def test_rest_configuration_rejects_missing_resources():
    ctx = ConnectorContext(
        tenant_id="t1",
        connection_id="c1",
        connector_id="universal_rest",
        configuration=ConnectionConfiguration(options={"adapter": {"base_url": "https://x.test"}}),
        credentials={},
        http_client=FakeHttpClient(),
    )
    result = RestAdapterConnector(ctx).validate_configuration(ctx.configuration)
    assert not result.valid


async def test_rest_pagination_and_field_mapping():
    def orders(**kwargs):
        page = int((kwargs.get("params") or {}).get("page", 1))
        if page == 2:
            return FakeResponse(200, {"data": {"total": 3, "items": [{"id": 3, "state": "new"}]}})
        return FakeResponse(
            200,
            {"data": {"total": 3, "items": [{"id": 1, "state": "done"}, {"id": 2, "state": "new"}]}},
        )

    client = FakeHttpClient({("GET", "/v1/orders"): orders})
    connector = RestAdapterConnector(_rest_ctx(client))
    page = await connector.fetch_records("orders")
    assert len(page.records) == 2
    assert page.records[0].payload == {"order_id": 1, "status": "done"}
    assert page.next_cursor == "2"
    assert page.has_more

    page2 = await connector.fetch_records("orders", cursor=page.next_cursor)
    assert len(page2.records) == 1
    assert page2.next_cursor is None


async def test_rest_incremental_sends_watermark():
    captured = {}

    def orders(**kwargs):
        captured.update(kwargs.get("params") or {})
        return FakeResponse(200, {"data": {"total": 0, "items": []}})

    client = FakeHttpClient({("GET", "/v1/orders"): orders})
    connector = RestAdapterConnector(_rest_ctx(client))
    await connector.fetch_incremental_records("orders", watermark="2024-01-01T00:00:00Z")
    assert captured["updated_since"] == "2024-01-01T00:00:00Z"


async def test_rest_http_error_raises():
    from app.core.errors import ConnectorError

    client = FakeHttpClient({("GET", "/v1/orders"): static(500, {"error": "boom"})})
    with pytest.raises(ConnectorError):
        await RestAdapterConnector(_rest_ctx(client)).fetch_records("orders")


# ---------------------------------------------------------------------------
# SQL adapter read-only enforcement
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM users",
        "UPDATE users SET admin = true",
        "INSERT INTO users VALUES (1)",
        "DROP TABLE users",
        "SELECT 1; DROP TABLE users",
        "SELECT * FROM users; DELETE FROM users",
        "ALTER TABLE users ADD COLUMN x int",
        "TRUNCATE users",
        "GRANT ALL ON users TO public",
    ],
)
def test_sql_adapter_rejects_non_read_only(sql: str):
    result = validate_read_only_sql(sql)
    assert not result.valid, f"should reject: {sql}"


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM orders",
        "SELECT id, name FROM orders WHERE id > 5",
        "WITH recent AS (SELECT * FROM orders) SELECT * FROM recent",
        "select count(*) from orders",
        "SELECT * FROM orders -- trailing comment",
    ],
)
def test_sql_adapter_allows_read_only(sql: str):
    result = validate_read_only_sql(sql)
    assert result.valid, f"should allow: {sql}: {result.errors}"


async def test_sql_adapter_refuses_execution_of_non_read_only():
    definition = {
        "dialect": "sqlite",
        "queries": [{"id": "bad", "sql": "DELETE FROM orders", "record_id_column": "id"}],
    }
    ctx = ConnectorContext(
        tenant_id="t1",
        connection_id="c1",
        connector_id="universal_sql",
        configuration=ConnectionConfiguration(database=":memory:", options={"adapter": definition}),
        credentials={},
    )
    connector = SqlAdapterConnector(ctx)
    # Configuration validation flags it...
    assert not connector.validate_configuration(ctx.configuration).valid
    # ...and execution refuses even if validation were bypassed.
    with pytest.raises(ValidationError):
        await connector.fetch_records("bad")


async def test_sql_adapter_executes_read_only_query_against_sqlite():
    import sqlite3
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, status TEXT)")
        conn.executemany(
            "INSERT INTO orders (id, status) VALUES (?, ?)", [(1, "open"), (2, "closed")]
        )
        conn.commit()
        conn.close()

        definition = {
            "dialect": "sqlite",
            "queries": [
                {
                    "id": "orders",
                    "sql": "SELECT id, status FROM orders",
                    "record_id_column": "id",
                }
            ],
        }
        ctx = ConnectorContext(
            tenant_id="t1",
            connection_id="c1",
            connector_id="universal_sql",
            configuration=ConnectionConfiguration(
                database=str(db_path), options={"adapter": definition}
            ),
            credentials={},
        )
        connector = SqlAdapterConnector(ctx)
        result = await connector.test_connection()
        assert result.success
        page = await connector.fetch_records("orders")
        assert len(page.records) == 2
        assert page.records[0].payload["status"] == "open"


# ---------------------------------------------------------------------------
# File adapter path confinement
# ---------------------------------------------------------------------------


async def test_file_adapter_blocks_path_outside_allowed_roots(tmp_path):
    from app.connectors.adapters.file_adapter import FileAdapterConnector

    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("sensitive")

    definition = {
        "transport": "local",
        "allowed_roots": [str(allowed)],
        "resources": [{"path": str(outside), "format": "csv"}],
    }
    ctx = ConnectorContext(
        tenant_id="t1",
        connection_id="c1",
        connector_id="universal_file",
        configuration=ConnectionConfiguration(options={"adapter": definition}),
        credentials={},
    )
    connector = FileAdapterConnector(ctx)
    with pytest.raises(EgressBlockedError):
        await connector.fetch_records(str(outside))


async def test_file_adapter_reads_csv_inside_allowed_root(tmp_path):
    from app.connectors.adapters.file_adapter import FileAdapterConnector

    allowed = tmp_path / "allowed"
    allowed.mkdir()
    csv_file = allowed / "orders.csv"
    csv_file.write_text("id,status\n1,open\n2,closed\n")

    definition = {
        "transport": "local",
        "allowed_roots": [str(allowed)],
        "resources": [{"path": str(csv_file), "format": "csv", "record_id_field": "id"}],
    }
    ctx = ConnectorContext(
        tenant_id="t1",
        connection_id="c1",
        connector_id="universal_file",
        configuration=ConnectionConfiguration(options={"adapter": definition}),
        credentials={},
    )
    connector = FileAdapterConnector(ctx)
    assert (await connector.test_connection()).success
    page = await connector.fetch_records(str(csv_file))
    assert [r.payload["status"] for r in page.records] == ["open", "closed"]
    assert page.records[0].source_record_id == "1"
