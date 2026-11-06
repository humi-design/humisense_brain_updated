"""Webhook signature verification tests."""

from __future__ import annotations

import time

import pytest

from app.core.errors import AuthenticationError
from app.core.webhook_security import (
    compute_hmac_sha256,
    verify_github_signature,
    verify_simple_sha256,
    verify_slack_signature,
    verify_webhook,
)

PAYLOAD = b'{"action":"opened","number":1}'
SECRET = "s3cr3t"


def test_github_signature_valid():
    sig = "sha256=" + compute_hmac_sha256(SECRET, PAYLOAD)
    assert verify_github_signature(SECRET, PAYLOAD, sig)


def test_github_signature_invalid():
    assert not verify_github_signature(SECRET, PAYLOAD, "sha256=deadbeef")
    assert not verify_github_signature(SECRET, PAYLOAD, None)


def test_simple_sha256_accepts_prefixed_and_bare():
    digest = compute_hmac_sha256(SECRET, PAYLOAD)
    assert verify_simple_sha256(SECRET, PAYLOAD, digest)
    assert verify_simple_sha256(SECRET, PAYLOAD, f"sha256={digest}")
    assert not verify_simple_sha256(SECRET, PAYLOAD, "wrong")


def test_slack_signature_valid():
    ts = str(int(time.time()))
    basestring = f"v0:{ts}:".encode() + PAYLOAD
    import hashlib
    import hmac

    sig = "v0=" + hmac.new(SECRET.encode(), basestring, hashlib.sha256).hexdigest()
    assert verify_slack_signature(SECRET, PAYLOAD, sig, ts)


def test_slack_signature_rejects_stale_timestamp():
    old_ts = str(int(time.time()) - 10_000)
    import hashlib
    import hmac

    basestring = f"v0:{old_ts}:".encode() + PAYLOAD
    sig = "v0=" + hmac.new(SECRET.encode(), basestring, hashlib.sha256).hexdigest()
    assert not verify_slack_signature(SECRET, PAYLOAD, sig, old_ts)


def test_verify_webhook_rejects_unsigned():
    with pytest.raises(AuthenticationError):
        verify_webhook(scheme="none", secret=SECRET, payload=PAYLOAD, signature=None)


def test_verify_webhook_rejects_bad_signature():
    with pytest.raises(AuthenticationError):
        verify_webhook(scheme="sha256", secret=SECRET, payload=PAYLOAD, signature="nope")


def test_verify_webhook_accepts_valid_github():
    sig = "sha256=" + compute_hmac_sha256(SECRET, PAYLOAD)
    verify_webhook(scheme="github", secret=SECRET, payload=PAYLOAD, signature=sig)


def test_verify_webhook_unknown_scheme_rejected():
    with pytest.raises(AuthenticationError):
        verify_webhook(scheme="rot13", secret=SECRET, payload=PAYLOAD, signature="x")
