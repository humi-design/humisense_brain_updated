"""API dependencies: authenticated principal resolution and authorization.

Identity model
--------------
The caller's identity comes from **one** of two mutually exclusive sources,
chosen by ``HUMISENSE_AUTH_MODE``:

``oidc``
    A bearer token is verified by :mod:`app.core.identity` (signature, issuer,
    audience, expiry, subject).  The verified subject is then resolved to a
    ``users`` membership row.  Role and tenant come from that row — never from
    the request.  This is the only mode permitted outside development.

``header``
    ``X-Tenant-Id`` / ``X-User-Id`` / ``X-User-Role`` are trusted.  Permitted
    only in development/test; ``Settings`` refuses to start otherwise.

In both modes the resulting :class:`Principal` is built server-side.  A client
cannot escalate by setting a header: in ``oidc`` mode ``X-User-Role`` is
ignored outright, and ``X-Tenant-Id`` may only *select* among memberships the
verified subject already holds.

Tenant selection
----------------
A subject with several memberships may pass ``X-Tenant-Id`` to choose which one
the request operates in.  The header is looked up against that subject's own
memberships; it can never create or grant one.  An unknown tenant yields 403,
not 404, because the subject is authenticated but not authorised there.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AuthenticationError, AuthorizationError
from app.core.identity import TokenVerificationError, TokenVerifier, VerifiedClaims
from app.core.logging import get_logger
from app.core.roles import ADMIN_ROLES, TENANT_ROLES
from app.db import models
from app.db.session import get_session_factory

logger = get_logger(__name__)

_VALID_ROLES = frozenset(TENANT_ROLES)


@dataclass(frozen=True)
class Principal:
    """The authenticated caller, resolved entirely server-side."""

    tenant_id: str
    user_id: str | None
    role: str
    #: Verified provider subject; ``None`` in header mode.
    subject: str | None = None
    #: How the identity was established — useful in audit detail.
    source: str = "header"

    @property
    def is_admin(self) -> bool:
        return self.role.lower() in ADMIN_ROLES


def get_db() -> Session:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


_verifier_cache: TokenVerifier | None = None


def _verifier() -> TokenVerifier | None:
    """Build (and cache) the configured token verifier."""
    global _verifier_cache
    if settings.auth_mode_normalised != "oidc":
        return None
    if _verifier_cache is None:
        _verifier_cache = TokenVerifier(settings)
    return _verifier_cache


def reset_verifier_cache() -> None:
    """Test helper: drop the cached verifier after settings change."""
    global _verifier_cache
    _verifier_cache = None


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise AuthenticationError("A bearer token is required.")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthenticationError("Authorization must use the Bearer scheme.")
    return token.strip()


def _memberships(db: Session, issuer: str, subject: str) -> list[models.User]:
    stmt = (
        select(models.User)
        .join(models.Tenant, models.Tenant.id == models.User.tenant_id)
        .where(
            models.User.external_issuer == issuer,
            models.User.external_subject == subject,
            models.User.is_active.is_(True),
            models.Tenant.is_active.is_(True),
        )
    )
    return list(db.execute(stmt).scalars().all())


def _principal_from_membership(
    membership: models.User, claims: VerifiedClaims | None, *, source: str
) -> Principal:
    role = (membership.role or "member").lower()
    if role not in _VALID_ROLES:
        # Defensive: a corrupt role must not silently become privileged.
        logger.warning("unknown_role", role=role)
        raise AuthorizationError("Your membership has an unrecognised role.")
    return Principal(
        tenant_id=membership.tenant_id,
        user_id=membership.id,
        role=role,
        subject=claims.subject if claims else None,
        source=source,
    )


def _resolve_oidc_principal(
    db: Session, claims: VerifiedClaims, tenant_header: str | None
) -> Principal:
    """Map verified claims onto a membership row, server-side."""
    memberships = _memberships(db, claims.issuer, claims.subject)
    if not memberships:
        # Authenticated with the provider but unknown to us: no membership.
        # 403 (not 404) — the identity is valid, the access is not granted.
        logger.warning("membership_not_found", subject_present=True)
        raise AuthorizationError(
            "This identity is not a member of any Humisense organization."
        )

    if tenant_header:
        for membership in memberships:
            if membership.tenant_id == tenant_header:
                return _principal_from_membership(membership, claims, source="oidc")
        # The subject is real but does not belong to the tenant they asked for.
        logger.warning("tenant_selection_denied", memberships=len(memberships))
        raise AuthorizationError("You do not have access to the requested organization.")

    if len(memberships) > 1:
        raise AuthorizationError(
            "Your account belongs to multiple organizations; specify one with "
            "the X-Tenant-Id header."
        )

    return _principal_from_membership(memberships[0], claims, source="oidc")


async def get_principal(
    db: Annotated[Session, Depends(get_db)],
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-Id")] = None,
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    """Resolve the caller to a trusted principal, or fail closed."""
    if settings.auth_mode_normalised == "oidc":
        verifier = _verifier()
        if verifier is None:  # pragma: no cover - guarded by Settings
            raise AuthenticationError("Authentication is not configured.")
        token = _bearer_token(authorization)
        try:
            claims = verifier.verify(token)
        except TokenVerificationError as exc:
            # Log the reason; never the token, and never echo the reason to the
            # caller (it would help an attacker probe configuration).
            logger.warning("token_rejected", reason=exc.reason)
            raise AuthenticationError("The supplied credentials are not valid.") from exc
        return _resolve_oidc_principal(db, claims, x_tenant_id)

    # --- development header mode ----------------------------------------
    if not settings.allows_header_identity:
        # Unreachable when Settings validation ran, but never fail open.
        raise AuthenticationError("Header authentication is not permitted here.")
    if not x_tenant_id:
        raise AuthenticationError("X-Tenant-Id header is required.")
    role = (x_user_role or "member").lower()
    if role not in _VALID_ROLES:
        raise AuthorizationError("Unrecognised role.")
    return Principal(
        tenant_id=x_tenant_id,
        user_id=x_user_id,
        role=role,
        subject=None,
        source="header",
    )


def require_role(*roles: str):
    """Authorize against the *server-resolved* role on the principal."""
    allowed = frozenset(r.lower() for r in roles)

    async def _checker(
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> Principal:
        if principal.role not in allowed:
            raise AuthorizationError(
                f"This action requires one of: {', '.join(sorted(allowed))}."
            )
        return principal

    return _checker


DbSession = Annotated[Session, Depends(get_db)]
CurrentPrincipal = Annotated[Principal, Depends(get_principal)]
AdminPrincipal = Annotated[Principal, Depends(require_role("owner", "admin"))]
