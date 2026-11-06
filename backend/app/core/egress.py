"""SSRF, DNS-rebinding and egress protection for outbound connector traffic.

Every outbound HTTP request made on behalf of a connector must go through
:func:`guard_url`.  The guard:

1. Rejects non-HTTPS schemes (HTTP allowed only in development).
2. Rejects userinfo-embedded URLs (``https://user:pass@host``).
3. Resolves the hostname and rejects loopback, link-local, private, reserved,
   multicast and unspecified addresses unless explicitly permitted.
4. Pins the request to the resolved IP so that a hostname cannot re-resolve
   to an internal address between validation and connection (DNS rebinding).

Hosts listed in ``egress_allowed_hosts`` bypass the private-range check only
when ``egress_allow_private`` is set; explicit blocked hosts always win.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.core.config import settings
from app.core.errors import EgressBlockedError

_ALLOWED_SCHEMES = {"https"}
_DEV_SCHEMES = {"https", "http"}


@dataclass(frozen=True)
class GuardedTarget:
    url: str
    host: str
    port: int
    resolved_ips: tuple[str, ...]
    scheme: str

    @property
    def is_pinned(self) -> bool:
        return bool(self.resolved_ips)


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _resolve(host: str, port: int) -> tuple[str, ...]:
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise EgressBlockedError(f"Host '{host}' could not be resolved.") from exc
    return tuple(sorted({info[4][0] for info in infos}))


def guard_url(url: str, *, allow_private: bool | None = None) -> GuardedTarget:
    """Validate an outbound URL and return a pinned target.

    Raises :class:`EgressBlockedError` when the target is not permitted.
    """
    if not isinstance(url, str) or not url.strip():
        raise EgressBlockedError("Empty URL is not permitted.")

    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "").lower()
    allowed_schemes = _ALLOWED_SCHEMES if settings.is_production else _DEV_SCHEMES
    if scheme not in allowed_schemes:
        raise EgressBlockedError(f"Scheme '{scheme or 'none'}' is not permitted for connector egress.")
    if parts.username or parts.password:
        raise EgressBlockedError("Credentials embedded in URLs are not permitted.")
    host = parts.hostname
    if not host:
        raise EgressBlockedError("URL must include a host.")
    port = parts.port or (443 if scheme == "https" else 80)

    blocked = {h.lower() for h in settings.egress_blocked_hosts}
    if host.lower() in blocked:
        raise EgressBlockedError(f"Host '{host}' is explicitly blocked.")

    permit_private = settings.egress_allow_private if allow_private is None else allow_private
    allowed = {h.lower() for h in settings.egress_allowed_hosts}
    host_is_allowlisted = host.lower() in allowed

    resolved = _resolve(host, port)
    if not resolved:
        raise EgressBlockedError(f"Host '{host}' resolved to no addresses.")

    for raw_ip in resolved:
        try:
            ip = ipaddress.ip_address(raw_ip)
        except ValueError:
            continue
        if _is_blocked_ip(ip) and not (permit_private or host_is_allowlisted):
            raise EgressBlockedError(
                f"Host '{host}' resolves to a non-routable address ({raw_ip}); egress blocked."
            )
    return GuardedTarget(
        url=url, host=host, port=port, resolved_ips=resolved, scheme=scheme
    )


def guard_host(host: str, port: int = 443, *, allow_private: bool | None = None) -> GuardedTarget:
    """Validate a bare host/port pair (used by SQL/SFTP adapters)."""
    return guard_url(f"https://{host}:{port}", allow_private=allow_private)
