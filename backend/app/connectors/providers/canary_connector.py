"""Canary Labs historian connector (read-only).

Verification status
-------------------
IMPLEMENTED, **not** INTEGRATION_VERIFIED.  No Canary installation was
reachable in the build environment, so this connector is written against the
documented Canary Web API surface and exercised only against clearly labelled
fixtures (``tests/fixtures/canary_*``).  It must not be presented as verified
until it has been run against a real historian with a valid licence.

Safety posture
--------------
* Read-only by design.  ``is_read_only = True``.
* The connector only issues GET requests.  There is no code path that writes
  tag values, setpoints, PLC logic or machine controls - and none may be added
  to Layer 1.
* Default operation is a bounded tag-data query, never an unbounded stream.

Documented endpoints used (Canary Web API):
    GET {base}/api/v1/tags                      - tag catalogue
    GET {base}/api/v1/tags/{tag}/data           - historical samples
    GET {base}/api/v1/views                     - configured views
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.connectors.base import BaseConnector, ConnectorContext
from app.core.errors import ConnectorAuthError, ConnectorError, ConnectorTransientError
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

# Fixture-backed sample shapes are documented in tests/fixtures/canary_*.
DEFAULT_SAMPLE_LIMIT = 5000
MAX_SAMPLE_LIMIT = 100_000


class CanaryConnector(BaseConnector):
    connector_id = "canary_labs"
    provider = "canary"
    is_read_only = True

    # -- configuration ---------------------------------------------------

    def validate_configuration(self, configuration: ConnectionConfiguration) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        base_url = configuration.base_url
        if not base_url:
            errors.append("base_url (the Canary Web API endpoint) is required.")
        elif not str(base_url).startswith(("http://", "https://")):
            errors.append("base_url must be an absolute URL.")
        creds = self.context.credentials or {}
        if not (creds.get("api_key") or creds.get("password") or creds.get("client_certificate")):
            errors.append("One of api_key, password or client_certificate is required.")
        if configuration.options.get("write_enabled"):
            errors.append("Canary connections are read-only; write_enabled is not permitted.")
        warnings.append(
            "Canary must be installed and the Web API enabled; network access to the "
            "historian host is required."
        )
        return ValidationResult(valid=not errors, errors=errors, warnings=warnings)

    def discover_capabilities(self) -> list[ConnectorCapability]:
        return [
            ConnectorCapability(capability=Capability.READ),
            ConnectorCapability(capability=Capability.SCHEMA_DISCOVERY),
            ConnectorCapability(capability=Capability.STREAM),
        ]

    # -- transport -------------------------------------------------------

    def _http(self) -> GuardedHttpClient:
        if self.context.http_client is not None:
            return self.context.http_client
        # Historians are typically on-premise; private access requires the
        # connection to be explicitly allowlisted at the deployment level.
        return GuardedHttpClient(
            allow_private=self.context.runtime_options.get("allow_private", None)
        )

    def _base(self) -> str:
        base = self.context.configuration.base_url
        if not base:
            raise ConnectorError("Canary base_url is not configured.")
        return base.rstrip("/")

    def _headers(self) -> dict[str, str]:
        creds = self.context.credentials or {}
        headers = {"Accept": "application/json", "User-Agent": "humisense-layer1"}
        if creds.get("api_key"):
            headers["X-API-Key"] = str(creds["api_key"])
        elif creds.get("username") and creds.get("password"):
            import base64

            raw = f"{creds['username']}:{creds['password']}".encode()
            headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
        return headers

    # -- lifecycle -------------------------------------------------------

    async def test_connection(self) -> ConnectorTestResult:
        import time

        started = time.perf_counter()
        try:
            response = await self._http().get(f"{self._base()}/api/v1/tags", headers=self._headers())
        except ConnectorTransientError as exc:
            return ConnectorTestResult(
                success=False,
                message=f"Canary historian is unreachable: {exc.message}",
            )
        latency = (time.perf_counter() - started) * 1000
        if response.status_code in {401, 403}:
            raise ConnectorAuthError("Canary rejected the supplied credentials.")
        if response.status_code >= 400:
            return ConnectorTestResult(
                success=False,
                message=f"Canary returned HTTP {response.status_code}.",
                latency_ms=latency,
            )
        return ConnectorTestResult(
            success=True,
            message="Canary historian responded to the read-only tag query.",
            latency_ms=latency,
            details={"endpoint": f"{self._base()}/api/v1/tags"},
        )

    async def discover_resources(self) -> list[ConnectorResource]:
        response = await self._http().get(f"{self._base()}/api/v1/tags", headers=self._headers())
        if response.status_code in {401, 403}:
            raise ConnectorAuthError("Canary rejected the supplied credentials.")
        if response.status_code >= 400:
            raise ConnectorError(f"Canary returned HTTP {response.status_code} listing tags.")
        body = response.json()
        tags = body.get("tags", body) if isinstance(body, dict) else body
        resources = [
            ConnectorResource(
                external_id=str(tag.get("name") or tag.get("id")),
                name=str(tag.get("name") or tag.get("id")),
                resource_type="historian_tag",
                metadata={"units": tag.get("units"), "description": tag.get("description")},
                read_only=True,
            )
            for tag in tags or []
        ]
        return resources

    async def fetch_records(
        self, resource_id: str, *, cursor: str | None = None, page_size: int | None = None
    ) -> FetchPage:
        return await self._fetch_tag_data(resource_id, cursor=cursor, page_size=page_size, since=None)

    async def fetch_incremental_records(
        self,
        resource_id: str,
        *,
        cursor: str | None = None,
        watermark: Any | None = None,
        page_size: int | None = None,
    ) -> FetchPage:
        since = watermark if isinstance(watermark, datetime) else None
        if isinstance(watermark, str):
            try:
                since = datetime.fromisoformat(watermark.replace("Z", "+00:00"))
            except ValueError:
                since = None
        return await self._fetch_tag_data(resource_id, cursor=cursor, page_size=page_size, since=since)

    async def _fetch_tag_data(
        self,
        tag: str,
        *,
        cursor: str | None,
        page_size: int | None,
        since: datetime | None,
    ) -> FetchPage:
        limit = min(page_size or DEFAULT_SAMPLE_LIMIT, MAX_SAMPLE_LIMIT)
        params: dict[str, Any] = {"limit": limit}
        if since:
            params["startTime"] = since.astimezone(timezone.utc).isoformat()
        if cursor:
            params["offset"] = cursor

        response = await self._http().get(
            f"{self._base()}/api/v1/tags/{tag}/data", headers=self._headers(), params=params
        )
        if response.status_code in {401, 403}:
            raise ConnectorAuthError("Canary rejected the supplied credentials.")
        if response.status_code >= 400:
            raise ConnectorError(f"Canary returned HTTP {response.status_code} for tag '{tag}'.")
        body = response.json()
        samples = body.get("data", body.get("samples", [])) if isinstance(body, dict) else body
        records = [self._to_record(sample, tag) for sample in samples or []]
        offset = int(cursor or 0)
        next_cursor = str(offset + limit) if len(records) == limit else None
        return FetchPage(records=records, next_cursor=next_cursor, has_more=next_cursor is not None)

    def _to_record(self, sample: dict[str, Any], tag: str) -> NormalizedRecord:
        timestamp = sample.get("timestamp") or sample.get("time") or sample.get("ts")
        observed = _parse_dt(timestamp)
        return NormalizedRecord(
            source_record_id=f"{tag}:{timestamp}",
            resource_id=tag,
            source_metadata={
                "provider": "canary",
                "connector_id": self.connector_id,
                "tag": tag,
                "quality": sample.get("quality"),
            },
            payload={
                "tag": tag,
                "timestamp": timestamp,
                "value": sample.get("value", sample.get("v")),
                "quality": sample.get("quality"),
            },
            observed_at=observed or datetime.now(timezone.utc),
            source_updated_at=observed,
        )

    async def subscribe_to_events(self, resource_id: str) -> dict[str, Any] | None:
        # Historians are polled; no subscription is registered.
        return None


def _parse_dt(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(float(raw), tz=timezone.utc)
    if isinstance(raw, str):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None
