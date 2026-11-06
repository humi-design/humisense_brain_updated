"""Slack connector (read-only).

Uses the Slack Web API ``auth.test`` for connection verification and
``conversations.list`` / ``conversations.history`` for resource discovery and
message retrieval.  Only the scopes actually granted to the token are
exercised.
"""

from __future__ import annotations

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

DEFAULT_API_BASE = "https://slack.com/api"


class SlackConnector(BaseConnector):
    connector_id = "slack"
    provider = "slack"
    is_read_only = True

    def validate_configuration(self, configuration: ConnectionConfiguration) -> ValidationResult:
        creds = self.context.credentials or {}
        errors: list[str] = []
        token = creds.get("token") or creds.get("bot_token") or creds.get("api_key")
        if not token:
            errors.append("A Slack bot or user token is required.")
        elif not str(token).startswith(("xoxb-", "xoxp-", "xoxa-")):
            errors.append("Slack tokens must start with xoxb-, xoxp- or xoxa-.")
        return ValidationResult(valid=not errors, errors=errors)

    def discover_capabilities(self) -> list[ConnectorCapability]:
        return [
            ConnectorCapability(capability=Capability.READ),
            ConnectorCapability(capability=Capability.INCREMENTAL),
            ConnectorCapability(capability=Capability.WEBHOOK),
        ]

    def _api_base(self) -> str:
        """Allows overriding the API root (compatible endpoints, fixtures)."""
        override = self.context.configuration.options.get("api_base")
        return str(override).rstrip("/") if override else DEFAULT_API_BASE

    def _http(self) -> GuardedHttpClient:
        if self.context.http_client is not None:
            return self.context.http_client
        return GuardedHttpClient()

    def _headers(self) -> dict[str, str]:
        creds = self.context.credentials or {}
        token = creds.get("token") or creds.get("bot_token") or creds.get("api_key")
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    async def test_connection(self) -> ConnectorTestResult:
        import time

        started = time.perf_counter()
        response = await self._http().post(f"{self._api_base()}/auth.test", headers=self._headers())
        latency = (time.perf_counter() - started) * 1000
        if response.status_code >= 400:
            return ConnectorTestResult(
                success=False, message=f"Slack returned HTTP {response.status_code}.", latency_ms=latency
            )
        body = response.json()
        if not body.get("ok"):
            error = body.get("error", "unknown_error")
            if error in {"invalid_auth", "not_authed", "token_revoked", "account_inactive"}:
                raise ConnectorAuthError(f"Slack authentication failed: {error}.")
            return ConnectorTestResult(success=False, message=f"Slack error: {error}.", latency_ms=latency)
        return ConnectorTestResult(
            success=True,
            message="Authenticated with Slack.",
            latency_ms=latency,
            account_identifier=body.get("team"),
            details={"team_id": body.get("team_id"), "user_id": body.get("user_id")},
        )

    async def discover_resources(self) -> list[ConnectorResource]:
        response = await self._http().post(
            f"{self._api_base()}/conversations.list",
            headers=self._headers(),
            json_body={"limit": 200, "types": "public_channel,private_channel"},
        )
        if response.status_code >= 400:
            raise ConnectorError(f"Slack returned HTTP {response.status_code} listing channels.")
        body = response.json()
        if not body.get("ok"):
            raise ConnectorError(f"Slack error listing channels: {body.get('error')}.")
        return [
            ConnectorResource(
                external_id=channel["id"],
                name=channel.get("name", channel["id"]),
                resource_type="channel",
                metadata={
                    "is_private": channel.get("is_private", False),
                    "is_archived": channel.get("is_archived", False),
                },
            )
            for channel in body.get("channels", [])
        ]

    async def fetch_records(
        self, resource_id: str, *, cursor: str | None = None, page_size: int | None = None
    ) -> FetchPage:
        return await self._fetch_history(resource_id, cursor=cursor, page_size=page_size, oldest=None)

    async def fetch_incremental_records(
        self,
        resource_id: str,
        *,
        cursor: str | None = None,
        watermark: Any | None = None,
        page_size: int | None = None,
    ) -> FetchPage:
        oldest = None
        if isinstance(watermark, datetime):
            oldest = str(watermark.timestamp())
        elif isinstance(watermark, (int, float)):
            oldest = str(float(watermark))
        elif isinstance(watermark, str):
            oldest = watermark
        return await self._fetch_history(resource_id, cursor=cursor, page_size=page_size, oldest=oldest)

    async def _fetch_history(
        self, channel_id: str, *, cursor: str | None, page_size: int | None, oldest: str | None
    ) -> FetchPage:
        payload: dict[str, Any] = {"channel": channel_id, "limit": min(page_size or 100, 200)}
        if cursor:
            payload["cursor"] = cursor
        if oldest:
            payload["oldest"] = oldest
        response = await self._http().post(
            f"{self._api_base()}/conversations.history", headers=self._headers(), json_body=payload
        )
        if response.status_code >= 400:
            raise ConnectorError(f"Slack returned HTTP {response.status_code} for channel history.")
        body = response.json()
        if not body.get("ok"):
            raise ConnectorError(f"Slack error fetching history: {body.get('error')}.")
        records = [self._to_record(msg, channel_id) for msg in body.get("messages", [])]
        next_cursor = (body.get("response_metadata") or {}).get("next_cursor") or None
        return FetchPage(records=records, next_cursor=next_cursor, has_more=bool(next_cursor))

    def _to_record(self, message: dict[str, Any], channel_id: str) -> NormalizedRecord:
        ts = message.get("ts")
        updated = None
        if ts:
            try:
                updated = datetime.fromtimestamp(float(ts), tz=timezone.utc)
            except (TypeError, ValueError):
                updated = None
        return NormalizedRecord(
            source_record_id=str(ts or message.get("client_msg_id") or ""),
            resource_id=channel_id,
            source_metadata={"provider": "slack", "connector_id": self.connector_id, "channel": channel_id},
            payload=message,
            source_updated_at=updated,
        )
