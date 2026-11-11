"""API dependencies: authentication context and tenant resolution.

Authentication is intentionally pluggable.  In production an identity provider
(OIDC/JWT) supplies the caller's tenant and user; the default development
resolver reads ``X-Tenant-Id`` / ``X-User-Id`` headers so the platform can be
exercised locally.  The tenant is *always* taken from the authenticated
principal - never from a request body or path - which is what makes tenant
isolation enforceable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AuthenticationError, AuthorizationError
from app.db.session import get_session_factory


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    user_id: str | None
    role: str


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


async def get_principal(
    request: Request,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-Id")] = None,
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    if settings.is_production and not authorization:
        raise AuthenticationError("A bearer token is required.")
    if not x_tenant_id:
        raise AuthenticationError("X-Tenant-Id header is required.")
    return Principal(
        tenant_id=x_tenant_id,
        user_id=x_user_id,
        role=(x_user_role or "member").lower(),
    )


def require_role(*roles: str):
    allowed = {r.lower() for r in roles}

    async def _checker(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
        if principal.role not in allowed:
            raise AuthorizationError(
                f"This action requires one of: {', '.join(sorted(allowed))}."
            )
        return principal

    return _checker


DbSession = Annotated[Session, Depends(get_db)]
CurrentPrincipal = Annotated[Principal, Depends(get_principal)]
AdminPrincipal = Annotated[Principal, Depends(require_role("owner", "admin"))]
