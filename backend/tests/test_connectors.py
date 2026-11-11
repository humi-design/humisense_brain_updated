"""Connector contract tests (MOCK transport).

These exercise the real connector code paths against a simulated provider.
They prove contract behaviour: auth handling, pagination, incremental sync,
normalisation and read-only guarantees.  They are NOT evidence of a live
provider integration - see docs/AUDIT.md for what was actually verified.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.connectors.base import ConnectorContext
from app.connectors.providers.canary_connector import CanaryConnector
from app.connectors.providers.github_connector import GitHubConnector
from app.connectors.providers.slack_connector import SlackConnector
from app.core.errors import ConnectorAuthError, ConnectorError, EgressBlockedError
from app.schemas.contracts import ConnectionConfiguration
from tests.fake_http import FakeHttpClient, FakeResponse, static

API = "https://api.github.com"


def _github_ctx(client, **options) -> ConnectorContext:
    return ConnectorContext(
        tenant_id="t1",
        connection_id="c1",
        connector_id="github",
        configuration=ConnectionConfiguration(
            base_url=API, options={"api_base": API, **options}
        ),
        credentials={"token": "ghp_mock"},
        http_client=client,
    )


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------


async def test_github_test_connection_success():
    client = FakeHttpClient(
        {
            ("GET", "/user"): static(
                200, {"login": "acme-bot", "type": "Bot"}, {"x-oauth-scopes": "repo, read:org"}
            )
        }
    )
    connector = GitHubConnector(_github_ctx(client))
    result = await connector.test_connection()
    assert result.success
    assert result.account_identifier == "acme-bot"
    assert "repo" in result.granted_scopes


async def test_github_invalid_token_raises_auth_error():
    client = FakeHttpClient({("GET", "/user"): static(401, {"message": "Bad credentials"})})
    connector = GitHubConnector(_github_ctx(client))
    with pytest.raises(ConnectorAuthError):
        await connector.test_connection()


async def test_github_pagination_follows_link_header():
    def issues(**kwargs):
        params = kwargs.get("params") or {}
        if params.get("page") == "2":
            return FakeResponse(200, [{"id": 2, "number": 2, "updated_at": "2024-01-02T00:00:00Z"}])
        return FakeResponse(
            200,
            [{"id": 1, "number": 1, "updated_at": "2024-01-01T00:00:00Z"}],
            {"link": f'<{API}/issues?page=2>; rel="next", <{API}/issues?page=2>; rel="last"'},
        )

    client = FakeHttpClient({("GET", "/issues"): issues})
    connector = GitHubConnector(_github_ctx(client))
    page = await connector.fetch_records("issues")
    assert [r.source_record_id for r in page.records] == ["1"]
    assert page.next_cursor == "2"
    assert page.has_more

    page2 = await connector.fetch_records("issues", cursor=page.next_cursor)
    assert [r.source_record_id for r in page2.records] == ["2"]
    assert page2.next_cursor is None


async def test_github_incremental_passes_since():
    captured = {}

    def issues(**kwargs):
        captured.update(kwargs.get("params") or {})
        return FakeResponse(200, [])

    client = FakeHttpClient({("GET", "/issues"): issues})
    connector = GitHubConnector(_github_ctx(client))
    watermark = datetime(2024, 3, 1, tzinfo=timezone.utc)
    await connector.fetch_incremental_records("issues", watermark=watermark)
    assert captured["since"] == "2024-03-01T00:00:00Z"


async def test_github_record_normalisation_preserves_source_id_and_metadata():
    client = FakeHttpClient(
        {("GET", "/issues"): static(200, [{"id": 99, "number": 7, "html_url": "u", "title": "t"}])}
    )
    connector = GitHubConnector(_github_ctx(client))
    page = await connector.fetch_records("issues")
    record = page.records[0]
    assert record.source_record_id == "99"
    assert record.source_metadata["number"] == 7
    assert record.payload["title"] == "t"


async def test_github_discover_resources_lists_repos():
    client = FakeHttpClient(
        {
            ("GET", "/user/repos"): static(
                200, [{"full_name": "acme/app", "private": True, "default_branch": "main"}]
            )
        }
    )
    connector = GitHubConnector(_github_ctx(client))
    resources = await connector.discover_resources()
    ids = {r.external_id for r in resources}
    assert "acme/app" in ids
    assert {"repos", "issues", "pulls"} <= ids


async def test_github_requires_token():
    ctx = ConnectorContext(
        tenant_id="t1",
        connection_id="c1",
        connector_id="github",
        configuration=ConnectionConfiguration(base_url=API, options={"api_base": API}),
        credentials={},
        http_client=FakeHttpClient(),
    )
    result = GitHubConnector(ctx).validate_configuration(ctx.configuration)
    assert not result.valid


# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------


def _slack_ctx(client, **options) -> ConnectorContext:
    return ConnectorContext(
        tenant_id="t1",
        connection_id="c1",
        connector_id="slack",
        configuration=ConnectionConfiguration(
            base_url="https://slack.com/api", options={"api_base": "https://slack.com/api", **options}
        ),
        credentials={"token": "xoxb-mock"},
        http_client=client,
    )


async def test_slack_auth_test_success():
    client = FakeHttpClient(
        {("POST", "/api/auth.test"): static(200, {"ok": True, "team": "Acme", "team_id": "T1"})}
    )
    result = await SlackConnector(_slack_ctx(client)).test_connection()
    assert result.success
    assert result.account_identifier == "Acme"


async def test_slack_invalid_auth_raises():
    client = FakeHttpClient({("POST", "/api/auth.test"): static(200, {"ok": False, "error": "invalid_auth"})})
    with pytest.raises(ConnectorAuthError):
        await SlackConnector(_slack_ctx(client)).test_connection()


async def test_slack_token_format_validated():
    ctx = ConnectorContext(
        tenant_id="t1",
        connection_id="c1",
        connector_id="slack",
        configuration=ConnectionConfiguration(options={"api_base": "https://slack.com/api"}),
        credentials={"token": "not-a-slack-token"},
        http_client=FakeHttpClient(),
    )
    result = SlackConnector(ctx).validate_configuration(ctx.configuration)
    assert not result.valid


async def test_slack_channel_discovery():
    client = FakeHttpClient(
        {
            ("POST", "/api/conversations.list"): static(
                200,
                {"ok": True, "channels": [{"id": "C1", "name": "general", "is_private": False}]},
            )
        }
    )
    resources = await SlackConnector(_slack_ctx(client)).discover_resources()
    assert resources[0].external_id == "C1"
    assert resources[0].name == "general"


async def test_slack_history_pagination_and_normalisation():
    def history(**kwargs):
        body = kwargs.get("json_body") or {}
        if body.get("cursor") == "next":
            return FakeResponse(200, {"ok": True, "messages": [{"ts": "1700000001.0", "text": "b"}]})
        return FakeResponse(
            200,
            {
                "ok": True,
                "messages": [{"ts": "1700000000.0", "text": "a"}],
                "response_metadata": {"next_cursor": "next"},
            },
        )

    client = FakeHttpClient({("POST", "/api/conversations.history"): history})
    connector = SlackConnector(_slack_ctx(client))
    page = await connector.fetch_records("C1")
    assert page.records[0].source_record_id == "1700000000.0"
    assert page.next_cursor == "next"
    assert page.records[0].source_updated_at is not None

    page2 = await connector.fetch_records("C1", cursor="next")
    assert page2.next_cursor is None


# ---------------------------------------------------------------------------
# Canary Labs (fixture-backed; NOT integration-verified)
# ---------------------------------------------------------------------------


def _canary_ctx(client, *, write_enabled: bool = False) -> ConnectorContext:
    return ConnectorContext(
        tenant_id="t1",
        connection_id="c1",
        connector_id="canary_labs",
        configuration=ConnectionConfiguration(
            base_url="https://canary.local:55235",
            options={"write_enabled": write_enabled, "allow_private": True},
        ),
        credentials={"api_key": "canary-mock"},
        http_client=client,
    )


async def test_canary_is_read_only_and_rejects_write():
    ctx = _canary_ctx(FakeHttpClient(), write_enabled=True)
    result = CanaryConnector(ctx).validate_configuration(ctx.configuration)
    assert not result.valid
    assert any("read-only" in e for e in result.errors)
    assert CanaryConnector(ctx).is_read_only is True


async def test_canary_test_connection_reads_tags():
    client = FakeHttpClient(
        {("GET", "/api/v1/tags"): static(200, {"tags": [{"name": "Line1.Temp", "units": "C"}]})}
    )
    result = await CanaryConnector(_canary_ctx(client)).test_connection()
    assert result.success


async def test_canary_tag_discovery():
    client = FakeHttpClient(
        {("GET", "/api/v1/tags"): static(200, {"tags": [{"name": "Line1.Temp", "units": "C"}]})}
    )
    resources = await CanaryConnector(_canary_ctx(client)).discover_resources()
    assert resources[0].external_id == "Line1.Temp"
    assert resources[0].read_only is True


async def test_canary_tag_data_normalisation():
    client = FakeHttpClient(
        {
            ("GET", "/api/v1/tags/Line1.Temp/data"): static(
                200,
                {"data": [{"timestamp": "2024-05-01T10:00:00Z", "value": 71.2, "quality": "good"}]},
            )
        }
    )
    page = await CanaryConnector(_canary_ctx(client)).fetch_records("Line1.Temp")
    record = page.records[0]
    assert record.payload["value"] == 71.2
    assert record.payload["tag"] == "Line1.Temp"
    assert record.source_metadata["quality"] == "good"


async def test_canary_uses_only_get_requests():
    """A read-only connector must never issue a mutating request."""
    client = FakeHttpClient(
        {("GET", "/api/v1/tags/Line1.Temp/data"): static(200, {"data": []})}
    )
    await CanaryConnector(_canary_ctx(client)).fetch_records("Line1.Temp")
    assert client.calls, "expected at least one request"
    assert all(call["method"] == "GET" for call in client.calls)


async def test_canary_auth_failure_raises():
    client = FakeHttpClient({("GET", "/api/v1/tags"): static(401, {"error": "unauthorized"})})
    with pytest.raises(ConnectorAuthError):
        await CanaryConnector(_canary_ctx(client)).test_connection()


async def test_canary_blocked_by_egress_guard_when_private_not_allowed():
    """Without an explicit allow_private opt-in the private historian host is blocked."""
    client = FakeHttpClient(
        {("GET", "/api/v1/tags"): static(200, {"tags": []})}
    )
    ctx = ConnectorContext(
        tenant_id="t1",
        connection_id="c1",
        connector_id="canary_labs",
        configuration=ConnectionConfiguration(
            base_url="https://canary.local:55235", options={"write_enabled": False}
        ),
        credentials={"api_key": "k"},
        http_client=None,  # use the real GuardedHttpClient so the guard runs
        runtime_options={"allow_private": False},
    )
    with pytest.raises(EgressBlockedError):
        await CanaryConnector(ctx).test_connection()


async def test_unknown_resource_raises():
    client = FakeHttpClient({})
    with pytest.raises(ConnectorError):
        await GitHubConnector(_github_ctx(client)).fetch_records("nope/nope/nope/extra")
