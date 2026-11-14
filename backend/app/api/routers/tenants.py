"""Tenant provisioning and membership administration.

Creating a tenant is a privileged, transactional operation.  It is reachable
by exactly two routes:

* **bootstrap** — while the platform has no tenants at all, and only when
  ``HUMISENSE_BOOTSTRAP_TOKEN`` is configured and presented.  This exists so a
  clean database can be set up; it closes permanently once a tenant exists.
* **admin** — an authenticated ``owner``/``admin`` of an existing tenant
  creating a further tenant.

There is no path by which an anonymous caller can create a tenant, or by which
any caller can grant themselves a membership.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, Header, status

from app.api.deps import (
    AdminPrincipal,
    CurrentPrincipal,
    DbSession,
    VerifiedSubjectDep,
    get_principal,
)
from app.api.schemas import (
    LinkIdentityIn,
    MembershipActiveIn,
    MembershipCreateIn,
    MembershipOut,
    SelfMembershipOut,
    TenantCreateIn,
    TenantOut,
    WhoAmIOut,
)
from app.core.config import settings
from app.core.errors import AuthorizationError
from app.db import models
from app.services.tenant_service import TenantService

router = APIRouter(prefix="/tenants", tags=["tenants"])


@dataclass(frozen=True)
class ProvisioningAuthority:
    """Who is allowed to create a tenant, and on what basis."""

    actor_id: str | None
    role: str


async def get_provisioning_authority(
    db: DbSession,
    x_bootstrap_token: Annotated[str | None, Header(alias="X-Bootstrap-Token")] = None,
    authorization: Annotated[str | None, Header()] = None,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-Id")] = None,
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> ProvisioningAuthority:
    """Resolve permission to create a tenant.

    Two cases, checked in this order:

    1. **Bootstrap** — no tenant exists yet.  The caller must present the
       configured bootstrap token.  This path closes permanently once any
       tenant exists.
    2. **Administrator** — a tenant exists, so the caller must be an
       authenticated ``owner``/``admin``.
    """
    service = TenantService(db)

    if service.bootstrap_required():
        service.assert_bootstrap_authorised(x_bootstrap_token, settings.bootstrap_token)
        return ProvisioningAuthority(actor_id=None, role="bootstrap")

    # A tenant already exists: this is an administrative action, so resolve a
    # real principal and check its role.
    principal = await get_principal(
        db=db,
        x_tenant_id=x_tenant_id,
        x_user_id=x_user_id,
        x_user_role=x_user_role,
        authorization=authorization,
    )
    if not principal.is_admin:
        raise AuthorizationError("Creating a tenant requires an administrator role.")
    return ProvisioningAuthority(actor_id=principal.user_id, role=principal.role)


ProvisioningAuthorityDep = Annotated[
    ProvisioningAuthority, Depends(get_provisioning_authority)
]


def _tenant_out(tenant: models.Tenant) -> TenantOut:
    return TenantOut(
        tenant_id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        is_active=tenant.is_active,
        created_at=tenant.created_at,
    )


def _membership_out(membership: models.User) -> MembershipOut:
    return MembershipOut(
        membership_id=membership.id,
        tenant_id=membership.tenant_id,
        email=membership.email,
        display_name=membership.display_name,
        role=membership.role,
        is_active=membership.is_active,
        identity_linked=bool(
            membership.external_issuer and membership.external_subject
        ),
        created_at=membership.created_at,
    )


@router.get("/whoami", response_model=WhoAmIOut)
def whoami(principal: CurrentPrincipal) -> WhoAmIOut:
    """Return the server-resolved identity.

    Useful to prove that ``X-Tenant-Id`` / ``X-User-Role`` are not trusted: the
    values returned here are the ones the backend resolved, not the ones sent.
    """
    return WhoAmIOut(
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        role=principal.role,
        subject=principal.subject,
        source=principal.source,
        is_admin=principal.is_admin,
        auth_mode=settings.auth_mode_normalised,
    )


@router.get("/memberships", response_model=list[SelfMembershipOut])
def list_own_memberships(
    subject: VerifiedSubjectDep,
    db: DbSession,
) -> list[SelfMembershipOut]:
    """List the caller's *own* active memberships.

    Self-scoped by construction: the query is filtered by the verified
    ``(issuer, subject)`` from the token, never by anything the caller sends.
    There is no parameter to widen it, so a caller cannot use this endpoint to
    enumerate another person's or another organization's memberships.

    This is the one endpoint reachable *before* a tenant is chosen, so it uses
    :func:`get_verified_subject` rather than :func:`get_principal`.  A user in
    several organizations would otherwise be refused as ambiguous by every
    endpoint — including the one that would tell them what to choose.

    The frontend uses this to offer a tenant choice.  Choosing one only
    *selects* a membership the subject already holds; every tenant-scoped
    request re-resolves it server-side, so a forged ``X-Tenant-Id`` still fails
    at the principal boundary.  This endpoint grants no access to tenant data.
    """
    if subject.source == "oidc":
        rows = TenantService(db).memberships_for_subject(
            subject.issuer or settings.auth_oidc_issuer, subject.subject
        )
    else:
        # Header mode (development/test only).  The subject is the user id the
        # caller supplied; the rows are still looked up rather than trusted.
        rows = (
            db.query(models.User)
            .join(models.Tenant, models.Tenant.id == models.User.tenant_id)
            .filter(
                models.User.id == subject.subject,
                models.User.is_active.is_(True),
                models.Tenant.is_active.is_(True),
            )
            .all()
        )

    if not rows:
        return []

    tenant_ids = [row.tenant_id for row in rows]
    tenants = {
        tenant.id: tenant
        for tenant in db.query(models.Tenant).filter(models.Tenant.id.in_(tenant_ids)).all()
    }
    return [
        SelfMembershipOut(
            tenant_id=row.tenant_id,
            tenant_name=tenants[row.tenant_id].name,
            tenant_slug=tenants[row.tenant_id].slug,
            role=row.role,
        )
        for row in rows
        if row.tenant_id in tenants
    ]


@router.get("/bootstrap-status")
def bootstrap_status(db: DbSession) -> dict:
    """Whether the platform still needs first-run provisioning."""
    service = TenantService(db)
    return {
        "bootstrap_required": service.bootstrap_required(),
        "bootstrap_enabled": bool(settings.bootstrap_token),
        "auth_mode": settings.auth_mode_normalised,
    }


@router.post("", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: TenantCreateIn,
    authority: ProvisioningAuthorityDep,
    db: DbSession,
) -> TenantOut:
    """Provision a tenant and its first owner.

    Authorisation is resolved by :data:`ProvisioningAuthority` before anything
    is written — either a valid bootstrap token (only while the platform has no
    tenants) or an authenticated tenant administrator.
    """
    service = TenantService(db)
    provisioned = service.create_tenant(
        name=payload.name,
        slug=payload.slug,
        owner_email=payload.owner_email,
        owner_display_name=payload.owner_display_name,
        owner_external_subject=payload.owner_external_subject,
        owner_external_issuer=(
            settings.auth_oidc_issuer if payload.owner_external_subject else None
        ),
        actor_id=authority.actor_id,
        actor_role=authority.role,
    )
    db.commit()
    return _tenant_out(provisioned.tenant)


@router.post(
    "/{tenant_id}/memberships",
    response_model=MembershipOut,
    status_code=status.HTTP_201_CREATED,
)
def create_membership(
    tenant_id: str,
    payload: MembershipCreateIn,
    principal: AdminPrincipal,
    db: DbSession,
) -> MembershipOut:
    """Add a membership. Requires an admin of *that* tenant."""
    if principal.tenant_id != tenant_id:
        raise AuthorizationError("You may only administer your own organization.")
    service = TenantService(db)
    membership = service.add_membership(
        tenant_id,
        email=payload.email,
        role=payload.role,
        display_name=payload.display_name,
        external_subject=payload.external_subject,
        external_issuer=settings.auth_oidc_issuer if payload.external_subject else None,
        actor_id=principal.user_id,
    )
    db.commit()
    return _membership_out(membership)


@router.get("/{tenant_id}/memberships", response_model=list[MembershipOut])
def list_memberships(
    tenant_id: str,
    principal: CurrentPrincipal,
    db: DbSession,
) -> list[MembershipOut]:
    if principal.tenant_id != tenant_id:
        raise AuthorizationError("You may only view your own organization.")
    rows = (
        db.query(models.User)
        .filter(models.User.tenant_id == tenant_id)
        .order_by(models.User.created_at)
        .all()
    )
    return [_membership_out(row) for row in rows]


@router.post("/{tenant_id}/memberships/{membership_id}/active", response_model=MembershipOut)
def set_membership_active(
    tenant_id: str,
    membership_id: str,
    payload: MembershipActiveIn,
    principal: AdminPrincipal,
    db: DbSession,
) -> MembershipOut:
    if principal.tenant_id != tenant_id:
        raise AuthorizationError("You may only administer your own organization.")
    service = TenantService(db)
    membership = service.set_membership_active(
        tenant_id, membership_id, active=payload.active, actor_id=principal.user_id
    )
    db.commit()
    return _membership_out(membership)


@router.post(
    "/{tenant_id}/memberships/{membership_id}/link-identity",
    response_model=MembershipOut,
)
def link_identity(
    tenant_id: str,
    membership_id: str,
    payload: LinkIdentityIn,
    principal: AdminPrincipal,
    db: DbSession,
) -> MembershipOut:
    if principal.tenant_id != tenant_id:
        raise AuthorizationError("You may only administer your own organization.")
    if not settings.auth_oidc_issuer:
        raise AuthorizationError("Identity linking requires a configured OIDC issuer.")
    service = TenantService(db)
    membership = service.link_identity(
        tenant_id,
        membership_id,
        issuer=settings.auth_oidc_issuer,
        subject=payload.external_subject,
        actor_id=principal.user_id,
    )
    db.commit()
    return _membership_out(membership)
