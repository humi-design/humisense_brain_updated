"""GitHub connector.

Verified against the public GitHub REST API v3 (see docs/AUDIT.md for the
verification record).  Supports read-only access to repositories, issues and
pull requests with link-header pagination and ``since`` incremental sync.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from app.connectors.base import BaseConnector, ConnectorContext
from app.core.errors import ConnectorAuthError, ConnectorError
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

DEFAULT_API_BASE = "https://api.github.com"
_LINK_RE = re.compile(r'<(?P<url>[^>]+)>;\s*rel="(?P<rel>[^"]+)"')

_RESOURCES = {
    "repos": "/user/repos",
    "issues": "/issues",
    "pulls": "/pulls",
}


class GitHubConnector(BaseConnector):
    connector_id = "github"
    provider = "github"
    is_read_only = True

    def validate_configuration(self, configuration: ConnectionConfiguration) -> ValidationResult:
        creds = self.context.credentials or {}
        errors: list[str] = []
        if not (creds.get("token") or creds.get("access_token") or creds.get("api_key")):
            errors.append("A GitHub personal access token or OAuth token is required.")
        return ValidationResult(valid=not errors, errors=errors)

    def discover_capabilities(self) -> list[ConnectorCapability]:
        return [
            ConnectorCapability(capability=Capability.READ),
            ConnectorCapability(capability=Capability.INCREMENTAL),
            ConnectorCapability(capability=Capability.WEBHOOK),
        ]

    def _api_base(self) -> str:
        """GitHub Enterprise Server and test fixtures can override the API root."""
        override = self.context.configuration.options.get("api_base")
        return str(override).rstrip("/") if override else DEFAULT_API_BASE

    def _http(self) -> GuardedHttpClient:
        if self.context.http_client is not None:
            return self.context.http_client
        return GuardedHttpClient()

    def _headers(self) -> dict[str, str]:
        creds = self.context.credentials or {}
        token = creds.get("token") or creds.get("access_token") or creds.get("api_key")
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "humisense-layer1",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def test_connection(self) -> ConnectorTestResult:
        import time

        started = time.perf_counter()
        response = await self._http().get(f"{self._api_base()}/user", headers=self._headers())
        latency = (time.perf_counter() - started) * 1000
        if response.status_code == 401:
            raise ConnectorAuthError("GitHub rejected the supplied token.")
        if response.status_code >= 400:
            return ConnectorTestResult(
                success=False, message=f"GitHub returned HTTP {response.status_code}.", latency_ms=latency
            )
        body = response.json()
        scopes = [s.strip() for s in response.headers.get("x-oauth-scopes", "").split(",") if s.strip()]
        return ConnectorTestResult(
            success=True,
            message="Authenticated with GitHub.",
            latency_ms=latency,
            account_identifier=body.get("login"),
            granted_scopes=scopes,
            details={"login": body.get("login"), "type": body.get("type")},
        )

    async def discover_resources(self) -> list[ConnectorResource]:
        resources: list[ConnectorResource] = [
            ConnectorResource(external_id=key, name=key, resource_type="github_resource")
            for key in _RESOURCES
        ]
        response = await self._http().get(
            f"{self._api_base()}/user/repos", headers=self._headers(), params={"per_page": 100}
        )
        if response.status_code < 400:
            for repo in response.json():
                resources.append(
                    ConnectorResource(
                        external_id=repo["full_name"],
                        name=repo["full_name"],
                        resource_type="repository",
                        metadata={"private": repo.get("private", False),
                                  "default_branch": repo.get("default_branch")},
                    )
                )
        return resources

    async def fetch_records(
        self, resource_id: str, *, cursor: str | None = None, page_size: int | None = None
    ) -> FetchPage:
        return await self._fetch(resource_id, cursor=cursor, page_size=page_size, since=None)

    async def fetch_incremental_records(
        self,
        resource_id: str,
        *,
        cursor: str | None = None,
        watermark: Any | None = None,
        page_size: int | None = None,
    ) -> FetchPage:
        since = None
        if isinstance(watermark, datetime):
            since = watermark.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        elif isinstance(watermark, str):
            since = watermark
        return await self._fetch(resource_id, cursor=cursor, page_size=page_size, since=since)

    async def _fetch(
        self, resource_id: str, *, cursor: str | None, page_size: int | None, since: str | None
    ) -> FetchPage:
        size = min(page_size or 100, 100)
        if resource_id in _RESOURCES:
            url = f"{self._api_base()}{_RESOURCES[resource_id]}"
            params: dict[str, Any] = {"per_page": size, "state": "all", "sort": "updated"}
            if since:
                params["since"] = since
        elif "/" in resource_id:
            url = f"{self._api_base()}/repos/{resource_id}/issues"
            params = {"per_page": size, "state": "all", "sort": "updated"}
            if since:
                params["since"] = since
        else:
            raise ConnectorError(f"Unknown GitHub resource '{resource_id}'.")
        if cursor:
            params["page"] = cursor

        response = await self._http().get(url, headers=self._headers(), params=params)
        if response.status_code == 401:
            raise ConnectorAuthError("GitHub rejected the supplied token.")
        if response.status_code >= 400:
            raise ConnectorError(f"GitHub returned HTTP {response.status_code} for {resource_id}.")
        items = response.json()
        if not isinstance(items, list):
            items = []

        records = [self._to_record(item, resource_id) for item in items]
        next_cursor = _next_page(response.headers.get("link"))
        return FetchPage(records=records, next_cursor=next_cursor, has_more=next_cursor is not None)

    def _to_record(self, item: dict[str, Any], resource_id: str) -> NormalizedRecord:
        updated = None
        if item.get("updated_at"):
            try:
                updated = datetime.fromisoformat(str(item["updated_at"]).replace("Z", "+00:00"))
            except ValueError:
                updated = None
        return NormalizedRecord(
            source_record_id=str(item.get("id") or item.get("number") or ""),
            resource_id=resource_id,
            source_metadata={
                "provider": "github",
                "connector_id": self.connector_id,
                "html_url": item.get("html_url"),
                "number": item.get("number"),
            },
            payload=item,
            source_updated_at=updated,
        )


def _next_page(link_header: str | None) -> str | None:
    if not link_header:
        return None
    for match in _LINK_RE.finditer(link_header):
        if match.group("rel") == "next":
            url = match.group("url")
            from urllib.parse import parse_qs, urlsplit

            query = parse_qs(urlsplit(url).query)
            page = query.get("page")
            if page:
                return page[0]
    return None
