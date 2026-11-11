"""Universal REST adapter.

Configures an arbitrary JSON REST API through a versioned, declarative
definition (auth, pagination, field mapping, incremental watermark).  The
definition is validated before it can be published; nothing here executes
AI-generated code - it only interprets a constrained, typed schema.

Definition shape (stored in ``configuration.options["adapter"]``)::

    {
      "base_url": "https://api.example.com/v1",
      "auth": {"type": "bearer_token", "header": "Authorization"},
      "resources": [
        {
          "id": "orders",
          "path": "/orders",
          "items_path": "data.items",
          "record_id_path": "id",
          "updated_at_path": "updated_at",
          "incremental_param": "updated_since",
          "pagination": {"strategy": "page", "page_param": "page",
                         "size_param": "per_page", "total_path": "data.total"},
          "fields": {"order_id": "id", "status": "state"}
        }
      ]
    }
"""

from __future__ import annotations

from typing import Any

from app.connectors.base import BaseConnector, ConnectorContext
from app.core.errors import ConnectorError, ValidationError
from app.core.http import GuardedHttpClient
from app.schemas.contracts import (
    Capability,
    ConnectionConfiguration,
    ConnectorCapability,
    ConnectorResource,
    ConnectorTestResult,
    FetchPage,
    NormalizedRecord,
    PaginationSpec,
    ValidationResult,
)


def _dig(data: Any, path: str | None) -> Any:
    if not path:
        return data
    current = data
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return current


class RestAdapterConnector(BaseConnector):
    connector_id = "universal_rest"
    provider = "humisense"
    is_read_only = False

    def _adapter(self) -> dict[str, Any]:
        return dict(self.context.configuration.options.get("adapter") or {})

    def _resource(self, resource_id: str) -> dict[str, Any]:
        for res in self._adapter().get("resources", []):
            if res.get("id") == resource_id:
                return res
        raise ConnectorError(f"Resource '{resource_id}' is not defined for this adapter.")

    def validate_configuration(self, configuration: ConnectionConfiguration) -> ValidationResult:
        adapter = dict(configuration.options.get("adapter") or {})
        errors: list[str] = []
        warnings: list[str] = []
        base_url = adapter.get("base_url") or configuration.base_url
        if not base_url:
            errors.append("base_url is required.")
        elif not str(base_url).startswith(("http://", "https://")):
            errors.append("base_url must be an absolute http(s) URL.")
        resources = adapter.get("resources")
        if not resources:
            errors.append("At least one resource must be defined.")
        else:
            seen: set[str] = set()
            for idx, res in enumerate(resources):
                rid = res.get("id")
                if not rid:
                    errors.append(f"resources[{idx}].id is required.")
                elif rid in seen:
                    errors.append(f"Duplicate resource id '{rid}'.")
                else:
                    seen.add(rid)
                if not res.get("path"):
                    errors.append(f"resources[{idx}].path is required.")
                pagination = res.get("pagination") or {}
                if pagination:
                    try:
                        PaginationSpec(**pagination)
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"resources[{idx}].pagination invalid: {exc}")
        if adapter.get("auth", {}).get("type") == "oauth2_client_credentials":
            warnings.append("OAuth client-credentials token refresh is handled by the sync engine.")
        return ValidationResult(valid=not errors, errors=errors, warnings=warnings)

    def discover_capabilities(self) -> list[ConnectorCapability]:
        return [
            ConnectorCapability(capability=Capability.READ),
            ConnectorCapability(capability=Capability.QUERY),
            ConnectorCapability(capability=Capability.INCREMENTAL),
        ]

    async def test_connection(self) -> ConnectorTestResult:
        adapter = self._adapter()
        base_url = adapter.get("base_url") or self.context.configuration.base_url
        if not base_url:
            return ConnectorTestResult(success=False, message="base_url is not configured.")
        resources = adapter.get("resources") or []
        probe = resources[0] if resources else None
        url = base_url.rstrip("/") + (probe.get("path", "/") if probe else "/")
        client = self._http()
        try:
            response = await client.get(url, headers=self._headers())
        except Exception as exc:  # noqa: BLE001
            return ConnectorTestResult(success=False, message=f"Request failed: {type(exc).__name__}")
        ok = 200 <= response.status_code < 300
        return ConnectorTestResult(
            success=ok,
            message=f"HTTP {response.status_code} from {url}",
            details={"status_code": response.status_code},
        )

    async def discover_resources(self) -> list[ConnectorResource]:
        return [
            ConnectorResource(
                external_id=res["id"],
                name=res.get("name", res["id"]),
                resource_type="api_resource",
                metadata={"path": res.get("path")},
                read_only=True,
            )
            for res in self._adapter().get("resources", [])
        ]

    def _http(self) -> GuardedHttpClient:
        if self.context.http_client is not None:
            return self.context.http_client
        return GuardedHttpClient(allow_private=self.context.runtime_options.get("allow_private"))

    def _headers(self) -> dict[str, str]:
        adapter = self._adapter()
        auth = adapter.get("auth") or {}
        headers = {"Accept": "application/json"}
        headers.update(adapter.get("default_headers") or {})
        creds = self.context.credentials or {}
        token = creds.get("token") or creds.get("api_key")
        if token:
            header = auth.get("header", "Authorization")
            scheme = auth.get("scheme", "Bearer")
            headers[header] = f"{scheme} {token}".strip()
        return headers

    async def fetch_records(
        self, resource_id: str, *, cursor: str | None = None, page_size: int | None = None
    ) -> FetchPage:
        return await self._fetch(resource_id, cursor=cursor, page_size=page_size, watermark=None)

    async def fetch_incremental_records(
        self,
        resource_id: str,
        *,
        cursor: str | None = None,
        watermark: Any | None = None,
        page_size: int | None = None,
    ) -> FetchPage:
        return await self._fetch(
            resource_id, cursor=cursor, page_size=page_size, watermark=watermark
        )

    async def _fetch(
        self, resource_id: str, *, cursor: str | None, page_size: int | None, watermark: Any | None
    ) -> FetchPage:
        adapter = self._adapter()
        base_url = adapter.get("base_url") or self.context.configuration.base_url
        res = self._resource(resource_id)
        pagination = PaginationSpec(**(res.get("pagination") or {}))
        size = (
            page_size
            or res.get("page_size")
            or adapter.get("page_size")
            or int(self.context.runtime_options.get("page_size", 100))
        )

        params: dict[str, Any] = dict(res.get("params") or {})
        if cursor and pagination.strategy == "cursor":
            params[pagination.cursor_param] = cursor
        elif cursor and pagination.strategy == "page":
            params[pagination.page_param] = cursor
        elif cursor and pagination.strategy == "offset":
            params[pagination.page_param] = cursor
        if pagination.strategy in {"page", "offset"}:
            params[pagination.size_param] = size
        if watermark and res.get("incremental_param"):
            params[res["incremental_param"]] = watermark

        url = base_url.rstrip("/") + res["path"]
        response = await self._http().get(url, headers=self._headers(), params=params)
        if response.status_code >= 400:
            raise ConnectorError(f"HTTP {response.status_code} fetching {resource_id}.")
        body = response.json()

        items = _dig(body, res.get("items_path")) if res.get("items_path") else body
        if not isinstance(items, list):
            items = items.get("items", []) if isinstance(items, dict) else []

        records = [self._to_record(item, res, resource_id) for item in items]
        next_cursor = self._next_cursor(body, res, pagination, cursor, len(items), size)
        return FetchPage(
            records=records,
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
        )

    def _to_record(self, item: dict[str, Any], res: dict[str, Any], resource_id: str) -> NormalizedRecord:
        rid_path = res.get("record_id_path", "id")
        source_id = str(_dig(item, rid_path) or "")
        mapping = res.get("fields") or {}
        payload = {target: _dig(item, src) for target, src in mapping.items()} if mapping else item
        updated_at = None
        if res.get("updated_at_path"):
            raw = _dig(item, res["updated_at_path"])
            updated_at = _parse_dt(raw)
        return NormalizedRecord(
            source_record_id=source_id,
            resource_id=resource_id,
            source_metadata={
                "provider": self.provider,
                "connector_id": self.connector_id,
                "mapping_applied": bool(mapping),
            },
            payload=payload,
            source_updated_at=updated_at,
        )

    def _next_cursor(
        self,
        body: Any,
        res: dict[str, Any],
        pagination: PaginationSpec,
        current: str | None,
        count: int,
        size: int,
    ) -> str | None:
        if count == 0:
            return None
        if pagination.strategy == "none":
            return None
        if pagination.strategy == "cursor":
            if pagination.cursor_json_path:
                nxt = _dig(body, pagination.cursor_json_path)
                return str(nxt) if nxt else None
            return None
        if pagination.strategy == "link_header":
            return None  # handled by provider-specific connectors
        total = _dig(body, pagination.total_json_path) if pagination.total_json_path else None
        try:
            total_int = int(total) if total is not None else None
        except (TypeError, ValueError):
            total_int = None

        if pagination.strategy == "offset":
            offset = int(current or 0)
            if total_int is not None and offset + count >= total_int:
                return None
            if count < size:
                return None
            return str(offset + size)

        # "page" strategy: page numbers are 1-based; ``current`` is the page
        # that was just fetched, and None means the first (implicit) page.
        page_number = int(current or 1)
        if total_int is not None and (page_number - 1) * size + count >= total_int:
            return None
        if count < size:
            return None
        return str(page_number + 1)


def _parse_dt(raw: Any):
    from datetime import datetime, timezone

    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(float(raw), tz=timezone.utc)
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None
