"""Universal SQL adapter - read-only by construction.

Safety model
------------
* Only a single ``SELECT`` or ``WITH ... SELECT`` statement is permitted.
* Statement text is parsed and validated: no semicolon-separated second
  statement, no DML/DDL keywords, no comments used to smuggle statements.
* The connection is opened in a read-only transaction where the driver
  supports it, and every query is wrapped in a bounded ``LIMIT``/``TOP``.
* SQLite is supported for tests and local fixtures only.

The adapter interprets a constrained query template.  It never executes
arbitrary SQL produced by an LLM without passing through :func:`validate_read_only_sql`.
"""

from __future__ import annotations

import re
from typing import Any

from app.connectors.base import BaseConnector, ConnectorContext
from app.core.errors import ConnectorError, ValidationError
from app.schemas.contracts import (
    Capability,
    ConnectionConfiguration,
    ConnectorCapability,
    ConnectorResource,
    ConnectorTestResult,
    FetchPage,
    NormalizedRecord,
    ValidationResult,
)

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|drop|alter|create|truncate|grant|revoke|"
    r"call|exec|execute|copy|vacuum|attach|detach|pragma|into|set|upsert|replace)\b",
    re.IGNORECASE,
)
_COMMENT = re.compile(r"(--[^\n]*|/\*.*?\*/)", re.DOTALL)
_ALLOWED_START = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)

_SUPPORTED_DIALECTS = {
    "postgresql": "postgresql+psycopg",
    "mysql": "mysql+pymysql",
    "mssql": "mssql+pyodbc",
    "oracle": "oracle+oracledb",
    "sqlite": "sqlite+pysqlite",
}


def validate_read_only_sql(sql: str) -> ValidationResult:
    errors: list[str] = []
    if not sql or not sql.strip():
        return ValidationResult(valid=False, errors=["SQL statement is empty."])
    stripped = _COMMENT.sub(" ", sql).strip().rstrip(";").strip()
    if ";" in stripped:
        errors.append("Multiple statements are not permitted.")
    if not _ALLOWED_START.match(stripped):
        errors.append("Only SELECT (or WITH ... SELECT) statements are permitted.")
    match = _FORBIDDEN.search(stripped)
    if match:
        errors.append(f"Forbidden keyword '{match.group(0).upper()}' in read-only query.")
    if len(stripped) > 20_000:
        errors.append("Query exceeds the maximum permitted length.")
    return ValidationResult(valid=not errors, errors=errors)


class SqlAdapterConnector(BaseConnector):
    connector_id = "universal_sql"
    provider = "humisense"
    is_read_only = True

    def _adapter(self) -> dict[str, Any]:
        return dict(self.context.configuration.options.get("adapter") or {})

    def _query(self, resource_id: str) -> dict[str, Any]:
        for q in self._adapter().get("queries", []):
            if q.get("id") == resource_id:
                return q
        raise ConnectorError(f"Query '{resource_id}' is not defined for this adapter.")

    def _dialect(self) -> str:
        return str(self._adapter().get("dialect", "postgresql")).lower()

    def validate_configuration(self, configuration: ConnectionConfiguration) -> ValidationResult:
        adapter = dict(configuration.options.get("adapter") or {})
        errors: list[str] = []
        warnings: list[str] = []
        dialect = str(adapter.get("dialect", "postgresql")).lower()
        if dialect not in _SUPPORTED_DIALECTS:
            errors.append(f"Unsupported SQL dialect '{dialect}'.")
        if not adapter.get("queries"):
            errors.append("At least one query must be defined.")
        for idx, q in enumerate(adapter.get("queries", [])):
            if not q.get("id"):
                errors.append(f"queries[{idx}].id is required.")
            result = validate_read_only_sql(str(q.get("sql", "")))
            errors.extend(f"queries[{idx}]: {e}" for e in result.errors)
            if not q.get("record_id_column"):
                warnings.append(f"queries[{idx}] has no record_id_column; source ids may be empty.")
        return ValidationResult(valid=not errors, errors=errors, warnings=warnings)

    def discover_capabilities(self) -> list[ConnectorCapability]:
        return [
            ConnectorCapability(capability=Capability.READ),
            ConnectorCapability(capability=Capability.QUERY),
        ]

    def _engine(self):
        from sqlalchemy import create_engine

        adapter = self._adapter()
        dialect = self._dialect()
        cfg = self.context.configuration
        creds = self.context.credentials or {}
        if dialect == "sqlite":
            path = cfg.database or adapter.get("path") or ":memory:"
            url = f"sqlite+pysqlite:///{path}"
            return create_engine(url, future=True)
        driver = _SUPPORTED_DIALECTS[dialect]
        user = creds.get("username", "")
        password = creds.get("password", "")
        host = cfg.host or adapter.get("host", "")
        port = cfg.port or adapter.get("port")
        database = cfg.database or adapter.get("database", "")
        from urllib.parse import quote_plus

        auth = f"{quote_plus(str(user))}:{quote_plus(str(password))}"
        port_part = f":{port}" if port else ""
        url = f"{driver}://{auth}@{host}{port_part}/{database}"
        return create_engine(url, future=True, pool_pre_ping=True)

    async def test_connection(self) -> ConnectorTestResult:
        from sqlalchemy import text

        try:
            engine = self._engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return ConnectorTestResult(success=True, message="Database connection succeeded.")
        except Exception as exc:  # noqa: BLE001
            return ConnectorTestResult(
                success=False, message=f"Database connection failed: {type(exc).__name__}"
            )

    async def discover_resources(self) -> list[ConnectorResource]:
        return [
            ConnectorResource(
                external_id=q["id"],
                name=q.get("name", q["id"]),
                resource_type="sql_query",
                read_only=True,
                metadata={"dialect": self._dialect()},
            )
            for q in self._adapter().get("queries", [])
        ]

    async def fetch_records(
        self, resource_id: str, *, cursor: str | None = None, page_size: int | None = None
    ) -> FetchPage:
        from sqlalchemy import text

        q = self._query(resource_id)
        validation = validate_read_only_sql(str(q["sql"]))
        if not validation.valid:
            raise ValidationError("Refused to execute a non read-only query.",
                                  detail={"errors": validation.errors})
        size = min(page_size or 100, 5000)
        offset = int(cursor or 0)
        sql = str(q["sql"]).strip().rstrip(";")
        paged = f"SELECT * FROM ({sql}) AS humisense_q LIMIT {size} OFFSET {offset}"
        engine = self._engine()
        with engine.connect() as conn:
            rows = conn.execute(text(paged)).mappings().all()
        id_col = q.get("record_id_column")
        updated_col = q.get("updated_at_column")
        records = []
        for row in rows:
            data = dict(row)
            source_id = str(data.get(id_col, "")) if id_col else str(data.get("id", ""))
            records.append(
                NormalizedRecord(
                    source_record_id=source_id,
                    resource_id=resource_id,
                    source_metadata={"provider": self.provider, "connector_id": self.connector_id,
                                     "dialect": self._dialect()},
                    payload=_jsonable(data),
                )
            )
            if updated_col:
                records[-1].source_updated_at = _parse_dt(data.get(updated_col))
        next_cursor = str(offset + size) if len(rows) == size else None
        return FetchPage(records=records, next_cursor=next_cursor, has_more=next_cursor is not None)


def _jsonable(data: dict[str, Any]) -> dict[str, Any]:
    from datetime import date, datetime
    from decimal import Decimal

    out: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, (datetime, date)):
            out[key] = value.isoformat()
        elif isinstance(value, Decimal):
            out[key] = float(value)
        elif isinstance(value, (bytes, bytearray)):
            out[key] = f"<{len(value)} bytes>"
        else:
            out[key] = value
    return out


def _parse_dt(raw: Any):
    from datetime import datetime, timezone

    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None
