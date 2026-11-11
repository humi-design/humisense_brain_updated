"""Universal GraphQL adapter (read-only queries)."""

from __future__ import annotations

from typing import Any

from app.connectors.adapters.rest_adapter import _dig, _parse_dt
from app.connectors.base import BaseConnector, ConnectorContext
from app.core.errors import ConnectorError
from app.core.http import GuardedHttpClient
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

_INTROSPECTION = {"query": "{ __typename }"}


class GraphQLAdapterConnector(BaseConnector):
    connector_id = "universal_graphql"
    provider = "humisense"
    is_read_only = False

    def _adapter(self) -> dict[str, Any]:
        return dict(self.context.configuration.options.get("adapter") or {})

    def _resource(self, resource_id: str) -> dict[str, Any]:
        for res in self._adapter().get("queries", []):
            if res.get("id") == resource_id:
                return res
        raise ConnectorError(f"Query '{resource_id}' is not defined for this adapter.")

    def validate_configuration(self, configuration: ConnectionConfiguration) -> ValidationResult:
        adapter = dict(configuration.options.get("adapter") or {})
        errors: list[str] = []
        endpoint = adapter.get("endpoint") or configuration.base_url
        if not endpoint:
            errors.append("endpoint is required.")
        for idx, q in enumerate(adapter.get("queries", [])):
            if not q.get("id"):
                errors.append(f"queries[{idx}].id is required.")
            if not q.get("query"):
                errors.append(f"queries[{idx}].query is required.")
            if "mutation" in str(q.get("query", "")).lower():
                errors.append(f"queries[{idx}] looks like a mutation; only queries are allowed.")
        return ValidationResult(valid=not errors, errors=errors)

    def discover_capabilities(self) -> list[ConnectorCapability]:
        return [
            ConnectorCapability(capability=Capability.READ),
            ConnectorCapability(capability=Capability.QUERY),
        ]

    def _http(self) -> GuardedHttpClient:
        if self.context.http_client is not None:
            return self.context.http_client
        return GuardedHttpClient(allow_private=self.context.runtime_options.get("allow_private"))

    def _headers(self) -> dict[str, str]:
        creds = self.context.credentials or {}
        token = creds.get("token") or creds.get("api_key")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def test_connection(self) -> ConnectorTestResult:
        adapter = self._adapter()
        endpoint = adapter.get("endpoint") or self.context.configuration.base_url
        if not endpoint:
            return ConnectorTestResult(success=False, message="endpoint is not configured.")
        response = await self._http().post(endpoint, headers=self._headers(), json_body=_INTROSPECTION)
        ok = response.status_code == 200 and not response.json().get("errors")
        return ConnectorTestResult(
            success=ok, message=f"HTTP {response.status_code}", details={"status_code": response.status_code}
        )

    async def discover_resources(self) -> list[ConnectorResource]:
        return [
            ConnectorResource(
                external_id=q["id"],
                name=q.get("name", q["id"]),
                resource_type="graphql_query",
                read_only=True,
            )
            for q in self._adapter().get("queries", [])
        ]

    async def fetch_records(
        self, resource_id: str, *, cursor: str | None = None, page_size: int | None = None
    ) -> FetchPage:
        adapter = self._adapter()
        endpoint = adapter.get("endpoint") or self.context.configuration.base_url
        res = self._resource(resource_id)
        variables = dict(res.get("variables") or {})
        if res.get("page_size_variable"):
            variables[res["page_size_variable"]] = page_size or 100
        if cursor and res.get("cursor_variable"):
            variables[res["cursor_variable"]] = cursor

        response = await self._http().post(
            endpoint, headers=self._headers(), json_body={"query": res["query"], "variables": variables}
        )
        if response.status_code >= 400:
            raise ConnectorError(f"GraphQL HTTP {response.status_code} for query '{resource_id}'.")
        body = response.json()
        if body.get("errors"):
            raise ConnectorError(f"GraphQL errors for '{resource_id}': {body['errors'][:1]}")
        items = _dig(body.get("data"), res.get("items_path")) or []
        if isinstance(items, dict):
            items = list(items.values())
        records = [
            NormalizedRecord(
                source_record_id=str(_dig(item, res.get("record_id_path", "id")) or ""),
                resource_id=resource_id,
                source_metadata={"provider": self.provider, "connector_id": self.connector_id},
                payload=item,
                source_updated_at=_parse_dt(_dig(item, res["updated_at_path"]))
                if res.get("updated_at_path")
                else None,
            )
            for item in items
        ]
        next_cursor = None
        if res.get("cursor_json_path"):
            nxt = _dig(body.get("data"), res["cursor_json_path"])
            next_cursor = str(nxt) if nxt else None
        return FetchPage(records=records, next_cursor=next_cursor, has_more=next_cursor is not None)
