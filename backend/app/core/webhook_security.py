"""Webhook signature verification and replay protection.

Supports HMAC-SHA256 signatures in the common provider formats plus GitHub's
``sha256=`` prefix, Slack's ``v0=`` timestamped scheme and a generic
``X-Signature-256`` header.  A timestamp tolerance window prevents replay of
old captures.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from app.core.config import settings
from app.core.errors import AuthenticationError


def _constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def compute_hmac_sha256(secret: str, payload: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify_github_signature(secret: str, payload: bytes, header: str | None) -> bool:
    if not header:
        return False
    expected = "sha256=" + compute_hmac_sha256(secret, payload)
    return _constant_time_compare(header, expected)


def verify_simple_sha256(secret: str, payload: bytes, header: str | None) -> bool:
    if not header:
        return False
    header = header.strip()
    if header.startswith("sha256="):
        header = header[len("sha256=") :]
    return _constant_time_compare(header.lower(), compute_hmac_sha256(secret, payload))


def verify_slack_signature(
    secret: str, payload: bytes, signature: str | None, timestamp: str | None
) -> bool:
    if not signature or not timestamp:
        return False
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    if abs(time.time() - ts) > settings.webhook_signature_tolerance_seconds:
        return False
    basestring = f"v0:{timestamp}:".encode("utf-8") + payload
    expected = "v0=" + hmac.new(secret.encode("utf-8"), basestring, hashlib.sha256).hexdigest()
    return _constant_time_compare(signature, expected)


def verify_webhook(
    *,
    scheme: str,
    secret: str,
    payload: bytes,
    signature: str | None,
    timestamp: str | None = None,
) -> None:
    """Raise :class:`AuthenticationError` when a webhook signature is invalid."""
    scheme = (scheme or "sha256").lower()
    if scheme in {"github", "github_sha256"}:
        ok = verify_github_signature(secret, payload, signature)
    elif scheme in {"slack", "slack_v0"}:
        ok = verify_slack_signature(secret, payload, signature, timestamp)
    elif scheme in {"sha256", "hmac_sha256", "generic"}:
        ok = verify_simple_sha256(secret, payload, signature)
    elif scheme in {"none", ""}:
        raise AuthenticationError("Unsigned webhooks are not accepted.")
    else:
        raise AuthenticationError(f"Unsupported webhook signature scheme '{scheme}'.")
    if not ok:
        raise AuthenticationError("Webhook signature verification failed.")
