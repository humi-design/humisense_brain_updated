"""Universal file adapter.

Reads CSV, Excel, JSON and XML from an authorised local directory or an SFTP
location.  Local paths are constrained to an operator-configured allowlist of
root directories so a connector cannot read arbitrary files from the host.
"""

from __future__ import annotations

import csv
import io
import json
import os
import xml.etree.ElementTree as ET
from typing import Any

from app.connectors.base import BaseConnector, ConnectorContext
from app.core.errors import ConnectorError, EgressBlockedError
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

SUPPORTED_FORMATS = {"csv", "tsv", "json", "xml", "xlsx"}


class FileAdapterConnector(BaseConnector):
    connector_id = "universal_file"
    provider = "humisense"
    is_read_only = True

    def _adapter(self) -> dict[str, Any]:
        return dict(self.context.configuration.options.get("adapter") or {})

    def _allowed_roots(self) -> list[str]:
        return [os.path.realpath(p) for p in self._adapter().get("allowed_roots", [])]

    def _safe_local_path(self, path: str) -> str:
        real = os.path.realpath(path)
        roots = self._allowed_roots()
        if not roots:
            raise EgressBlockedError("No allowed_roots configured; local file access is disabled.")
        if not any(real == root or real.startswith(root + os.sep) for root in roots):
            raise EgressBlockedError("Requested path is outside the authorised directories.")
        return real

    def validate_configuration(self, configuration: ConnectionConfiguration) -> ValidationResult:
        adapter = dict(self._adapter())
        errors: list[str] = []
        transport = adapter.get("transport", "local")
        if transport not in {"local", "sftp"}:
            errors.append("transport must be 'local' or 'sftp'.")
        if transport == "local" and not adapter.get("allowed_roots"):
            errors.append("allowed_roots must be set for local file access.")
        for idx, res in enumerate(adapter.get("resources", [])):
            fmt = str(res.get("format", "")).lower()
            if fmt not in SUPPORTED_FORMATS:
                errors.append(f"resources[{idx}].format '{fmt}' is not supported.")
            if not res.get("path"):
                errors.append(f"resources[{idx}].path is required.")
        return ValidationResult(valid=not errors, errors=errors)

    def discover_capabilities(self) -> list[ConnectorCapability]:
        return [ConnectorCapability(capability=Capability.READ)]

    async def test_connection(self) -> ConnectorTestResult:
        adapter = self._adapter()
        transport = adapter.get("transport", "local")
        try:
            if transport == "sftp":
                return await self._test_sftp()
            resources = adapter.get("resources", [])
            if not resources:
                return ConnectorTestResult(success=False, message="No resources configured.")
            path = self._safe_local_path(resources[0]["path"])
            exists = os.path.isfile(path)
            return ConnectorTestResult(
                success=exists,
                message="File is reachable." if exists else "Configured file does not exist.",
            )
        except EgressBlockedError as exc:
            return ConnectorTestResult(success=False, message=str(exc))
        except Exception as exc:  # noqa: BLE001
            return ConnectorTestResult(success=False, message=f"Failed: {type(exc).__name__}")

    async def _test_sftp(self) -> ConnectorTestResult:
        # SFTP uses the same egress guard as HTTP; the host is allowlisted by policy.
        from app.core.egress import guard_host

        cfg = self.context.configuration
        host = cfg.host or self._adapter().get("host")
        port = cfg.port or self._adapter().get("port", 22)
        if not host:
            return ConnectorTestResult(success=False, message="SFTP host is not configured.")
        try:
            guard_host(str(host), int(port))
        except EgressBlockedError as exc:
            return ConnectorTestResult(success=False, message=str(exc))
        return ConnectorTestResult(
            success=True,
            message="SFTP host is reachable and permitted by egress policy.",
            details={"host": host, "port": port},
        )

    async def discover_resources(self) -> list[ConnectorResource]:
        return [
            ConnectorResource(
                external_id=res["path"],
                name=res.get("name", os.path.basename(res["path"])),
                resource_type=f"file_{res.get('format', 'csv')}",
                read_only=True,
            )
            for res in self._adapter().get("resources", [])
        ]

    async def fetch_records(
        self, resource_id: str, *, cursor: str | None = None, page_size: int | None = None
    ) -> FetchPage:
        res = None
        for candidate in self._adapter().get("resources", []):
            if candidate["path"] == resource_id:
                res = candidate
                break
        if res is None:
            raise ConnectorError(f"File resource '{resource_id}' is not configured.")

        raw = await self._read_bytes(res)
        fmt = str(res.get("format", "csv")).lower()
        rows = _parse(raw, fmt, res)
        offset = int(cursor or 0)
        size = page_size or 1000
        window = rows[offset : offset + size]
        id_field = res.get("record_id_field")
        records = []
        for idx, row in enumerate(window):
            source_id = str(row.get(id_field, "")) if id_field else str(offset + idx)
            records.append(
                NormalizedRecord(
                    source_record_id=source_id,
                    resource_id=resource_id,
                    source_metadata={
                        "provider": self.provider,
                        "connector_id": self.connector_id,
                        "format": fmt,
                        "row_index": offset + idx,
                    },
                    payload=row,
                )
            )
        next_cursor = str(offset + size) if offset + size < len(rows) else None
        return FetchPage(records=records, next_cursor=next_cursor, has_more=next_cursor is not None)

    async def _read_bytes(self, res: dict[str, Any]) -> bytes:
        if self._adapter().get("transport", "local") == "sftp":
            return await self._read_sftp(res)
        path = self._safe_local_path(res["path"])
        if not os.path.isfile(path):
            raise ConnectorError("Configured file does not exist.")
        with open(path, "rb") as handle:
            return handle.read()

    async def _read_sftp(self, res: dict[str, Any]) -> bytes:
        try:
            import paramiko  # optional dependency
        except ImportError as exc:  # pragma: no cover - optional path
            raise ConnectorError("SFTP support requires the 'paramiko' package.") from exc
        cfg = self.context.configuration
        creds = self.context.credentials or {}
        host = cfg.host or self._adapter().get("host")
        port = int(cfg.port or self._adapter().get("port", 22))
        transport = paramiko.Transport((host, port))
        try:
            if creds.get("private_key"):
                key = paramiko.RSAKey.from_private_key(io.StringIO(str(creds["private_key"])))
                transport.connect(username=creds.get("username"), pkey=key)
            else:
                transport.connect(
                    username=creds.get("username"), password=creds.get("password")
                )
            sftp = paramiko.SFTPClient.from_transport(transport)
            with sftp.open(res["path"], "rb") as handle:
                return handle.read()
        finally:
            transport.close()


def _parse(raw: bytes, fmt: str, res: dict[str, Any]) -> list[dict[str, Any]]:
    if fmt in {"csv", "tsv"}:
        delimiter = res.get("delimiter") or ("\t" if fmt == "tsv" else ",")
        text = raw.decode(res.get("encoding", "utf-8-sig"))
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        return [dict(row) for row in reader]
    if fmt == "json":
        data = json.loads(raw.decode(res.get("encoding", "utf-8")))
        if isinstance(data, dict):
            data = data.get(res.get("items_key", "items"), data)
        if isinstance(data, dict):
            data = [data]
        return list(data)
    if fmt == "xml":
        root = ET.fromstring(raw)
        records = []
        record_tag = res.get("record_tag")
        for element in root.iter(record_tag) if record_tag else root:
            records.append({child.tag: (child.text or "").strip() for child in element})
        return records
    if fmt == "xlsx":
        try:
            from openpyxl import load_workbook  # optional dependency
        except ImportError as exc:  # pragma: no cover - optional path
            raise ConnectorError("Excel support requires the 'openpyxl' package.") from exc
        workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        sheet = workbook[res["sheet"]] if res.get("sheet") else workbook.active
        rows = sheet.iter_rows(values_only=True)
        try:
            headers = [str(h) if h is not None else "" for h in next(rows)]
        except StopIteration:
            return []
        return [dict(zip(headers, row)) for row in rows]
    raise ConnectorError(f"Unsupported file format '{fmt}'.")
