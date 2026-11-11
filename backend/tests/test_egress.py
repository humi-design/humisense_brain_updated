"""SSRF / egress protection tests.

Proves the guard rejects loopback, private, link-local, metadata and
non-HTTPS targets, and that userinfo-embedded URLs are refused.
"""

from __future__ import annotations

import socket

import pytest

from app.core import egress
from app.core.errors import EgressBlockedError


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch):
    """Resolve every hostname to a public IP unless a test overrides it."""
    def fake_getaddrinfo(host, port, **kwargs):  # noqa: ANN001
        if host in {"localhost", "internal.example.com", "metadata.google.internal"}:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]
        if host == "169.254.example.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", port))]
        if host == "private.example.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", port))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


def test_public_https_allowed():
    target = egress.guard_url("https://api.example.com/v1/items")
    assert target.host == "api.example.com"
    assert target.resolved_ips == ("93.184.216.34",)


def test_loopback_blocked():
    with pytest.raises(EgressBlockedError):
        egress.guard_url("https://localhost/admin")


def test_private_range_blocked():
    with pytest.raises(EgressBlockedError):
        egress.guard_url("https://private.example.com/secret")


def test_link_local_metadata_blocked():
    with pytest.raises(EgressBlockedError):
        egress.guard_url("https://169.254.example.com/latest/meta-data")


def test_cloud_metadata_host_blocked():
    with pytest.raises(EgressBlockedError):
        egress.guard_url("https://metadata.google.internal/computeMetadata/v1/")


def test_userinfo_in_url_blocked():
    with pytest.raises(EgressBlockedError):
        egress.guard_url("https://user:pass@api.example.com/v1")


def test_non_http_scheme_blocked():
    with pytest.raises(EgressBlockedError):
        egress.guard_url("file:///etc/passwd")
    with pytest.raises(EgressBlockedError):
        egress.guard_url("gopher://api.example.com/")


def test_empty_url_blocked():
    with pytest.raises(EgressBlockedError):
        egress.guard_url("")


def test_explicit_blocklist_wins(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "egress_blocked_hosts", ["api.example.com"])
    with pytest.raises(EgressBlockedError):
        egress.guard_url("https://api.example.com/v1")


def test_allow_private_opt_in(monkeypatch):
    target = egress.guard_url("https://private.example.com/x", allow_private=True)
    assert target.host == "private.example.com"


def test_allowlisted_host_permits_private(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "egress_allowed_hosts", ["private.example.com"])
    target = egress.guard_url("https://private.example.com/x")
    assert target.host == "private.example.com"
