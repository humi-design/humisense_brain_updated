"""OIDC/JWT access-token verification.

This module is the *only* place a bearer token is turned into trusted claims.
It never accepts a key, issuer or algorithm from the request: all of them come
from server configuration (see ``app.core.config.Settings``).

Verification performed on every token:

* signature, against the configured JWKS (or HMAC secret);
* ``alg`` restricted to an explicit allow-list — ``none`` is never accepted,
  and symmetric algorithms cannot be enabled alongside a JWKS URL;
* ``iss`` must equal the configured issuer exactly;
* ``aud`` must contain the configured audience;
* ``exp`` and ``nbf`` are enforced, with a small configurable leeway;
* ``sub`` must be present and non-empty.

Anything that fails raises :class:`TokenVerificationError`, which the API layer
maps to 401.  Failures never reveal *why* to the caller beyond a generic
message; the reason is logged server-side without the token value.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import jwt
from jwt import PyJWKClient

from app.core.config import Settings
from app.core.errors import ConfigurationError
from app.core.logging import get_logger

logger = get_logger(__name__)

# Claims that must be present for a token to be usable as an identity.
REQUIRED_CLAIMS = ("exp", "iss", "aud", "sub")

# PyJWT's own symmetric algorithms.  Kept here so the allow-list check in
# ``config`` and the decode call cannot drift apart.
_SYMMETRIC_ALGORITHMS = {"HS256", "HS384", "HS512"}


class TokenVerificationError(Exception):
    """A bearer token could not be trusted.

    Deliberately carries no detail: the caller must not be able to distinguish
    "bad signature" from "unknown key" from "expired".
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class VerifiedClaims:
    """Claims from a token whose signature and standard claims were verified."""

    subject: str
    issuer: str
    audience: tuple[str, ...]
    expires_at: int | None
    email: str | None
    name: str | None
    claims: dict[str, Any] = field(default_factory=dict)

    def claim(self, name: str | None) -> Any:
        """Read an arbitrary claim, returning ``None`` when unset or unnamed."""
        if not name:
            return None
        return self.claims.get(name)


class TokenVerifier:
    """Verifies access tokens against configured, trusted key material.

    One instance is created per application and reused, so the JWKS cache is
    shared across requests.
    """

    def __init__(self, settings: Settings) -> None:
        self._issuer = settings.auth_oidc_issuer
        self._audience = settings.auth_oidc_audience
        self._leeway = max(0, settings.auth_leeway_seconds)
        self._algorithms = [
            a.strip().upper() for a in settings.auth_oidc_algorithms if a.strip()
        ]
        self._hmac_secret = settings.auth_oidc_hmac_secret
        self._jwks_url = settings.auth_oidc_jwks_url

        if not self._issuer or not self._audience:
            # ``Settings`` already refuses to start in this state; this is a
            # second line of defence for anyone constructing a verifier directly.
            raise ConfigurationError(
                "OIDC verification requires an issuer and an audience."
            )

        self._jwks_client: PyJWKClient | None = None
        if self._jwks_url:
            self._jwks_client = PyJWKClient(
                self._jwks_url,
                cache_keys=True,
                cache_jwk_set=True,
                lifespan=max(1, settings.auth_jwks_cache_seconds),
            )

    # -- public API -------------------------------------------------------

    def verify(self, token: str) -> VerifiedClaims:
        """Verify a compact JWT and return its trusted claims."""
        if not token or not token.strip():
            raise TokenVerificationError("empty_token")

        token = token.strip()

        try:
            key = self._resolve_key(token)
        except TokenVerificationError:
            raise
        except Exception as exc:  # key lookup is provider-controlled
            logger.warning("jwks_lookup_failed", error=type(exc).__name__)
            raise TokenVerificationError("key_unavailable") from exc

        options = {
            "require": list(REQUIRED_CLAIMS),
            "verify_signature": True,
            "verify_exp": True,
            "verify_nbf": True,
            "verify_iat": False,
            "verify_aud": True,
            "verify_iss": True,
        }

        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=self._algorithms,
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway,
                options=options,
            )
        except jwt.ExpiredSignatureError as exc:
            raise TokenVerificationError("expired") from exc
        except jwt.ImmatureSignatureError as exc:
            raise TokenVerificationError("not_yet_valid") from exc
        except jwt.InvalidAudienceError as exc:
            raise TokenVerificationError("bad_audience") from exc
        except jwt.InvalidIssuerError as exc:
            raise TokenVerificationError("bad_issuer") from exc
        except jwt.MissingRequiredClaimError as exc:
            raise TokenVerificationError(f"missing_claim:{exc.claim}") from exc
        except jwt.InvalidAlgorithmError as exc:
            raise TokenVerificationError("bad_algorithm") from exc
        except jwt.InvalidSignatureError as exc:
            raise TokenVerificationError("bad_signature") from exc
        except jwt.DecodeError as exc:
            raise TokenVerificationError("malformed") from exc
        except jwt.PyJWTError as exc:  # catch-all for the library
            raise TokenVerificationError("invalid") from exc

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject.strip():
            raise TokenVerificationError("missing_claim:sub")

        return VerifiedClaims(
            subject=subject.strip(),
            issuer=str(claims.get("iss", "")),
            audience=self._audience_tuple(claims.get("aud")),
            expires_at=claims.get("exp"),
            email=_as_str(claims.get("email")),
            name=_as_str(claims.get("name")) or _as_str(claims.get("preferred_username")),
            claims=claims,
        )

    # -- internals --------------------------------------------------------

    def _resolve_key(self, token: str) -> Any:
        """Return the verification key without ever trusting request input.

        For asymmetric algorithms the key is selected by ``kid`` from the
        configured JWKS.  For symmetric algorithms the configured secret is
        used.  The algorithm set is already restricted by ``Settings``.
        """
        if self._jwks_client is not None:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            return signing_key.key
        if self._hmac_secret:
            return self._hmac_secret
        # Unreachable when Settings validation ran, but never fail open.
        raise ConfigurationError("No trusted key source is configured.")

    @staticmethod
    def _audience_tuple(value: Any) -> tuple[str, ...]:
        if isinstance(value, str):
            return (value,)
        if isinstance(value, (list, tuple)):
            return tuple(str(v) for v in value)
        return ()


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build_verifier(settings: Settings) -> TokenVerifier | None:
    """Construct a verifier for the configured auth mode.

    Returns ``None`` when header identity is in use.  Raises
    :class:`ConfigurationError` if ``oidc`` is selected but unusable, so the
    application fails to start rather than serving unauthenticated traffic.
    """
    if settings.auth_mode_normalised != "oidc":
        return None
    return TokenVerifier(settings)


def current_timestamp() -> int:
    """Clock indirection so tests can reason about expiry deterministically."""
    return int(time.time())
