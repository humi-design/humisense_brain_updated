"""Tenant and membership provisioning.

Provisioning is the controlled process by which an organization gets a
``tenants`` row and at least one owner.  It exists because
``connections.tenant_id`` (and now every other tenant-scoped table) has a
foreign key to ``tenants.id``: without a tenant row the very first connection
cannot be created.

Rules enforced here
-------------------
* Every operation is transactional — a failure leaves no partial state.
* Creating a tenant also creates its first owner membership, in the same
  transaction, so a tenant is never ownerless.
* The first tenant (bootstrap) is allowed only with a configured bootstrap
  token.  After that, creating a tenant requires an authenticated platform
  administrator, and adding a membership requires tenant admin rights.
* Duplicates are rejected explicitly rather than surfacing as an
  ``IntegrityError``.
* Every action is audited.
"""

from __future__ import annotations

import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.logging import get_logger
from app.core.roles import TENANT_ROLES
from app.db import models
from app.schemas.contracts import AuditAction

logger = get_logger(__name__)

_SLUG_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{1,62}[a-z0-9])?$")


@dataclass(frozen=True)
class ProvisionedTenant:
    tenant: models.Tenant
    owner: models.User


def _now() -> datetime:
    return datetime.now(UTC)


def slugify(value: str) -> str:
    """Derive a DNS-ish slug from a display name."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:63]


class TenantService:
    """Transactional tenant and membership administration."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # -- audit -----------------------------------------------------------

    def _audit(
        self,
        tenant_id: str,
        action: AuditAction,
        *,
        actor_id: str | None,
        resource_type: str,
        resource_id: str | None,
        detail: dict | None = None,
    ) -> None:
        self.session.add(
            models.AuditLog(
                tenant_id=tenant_id,
                actor_id=actor_id,
                action=action.value,
                resource_type=resource_type,
                resource_id=resource_id,
                detail=detail or {},
            )
        )

    # -- queries ---------------------------------------------------------

    def find_by_slug(self, slug: str) -> models.Tenant | None:
        return self.session.execute(
            select(models.Tenant).where(models.Tenant.slug == slug)
        ).scalar_one_or_none()

    def get_tenant(self, tenant_id: str) -> models.Tenant:
        tenant = self.session.get(models.Tenant, tenant_id)
        if tenant is None:
            raise NotFoundError("Tenant not found.")
        return tenant

    # -- provisioning ----------------------------------------------------

    def create_tenant(
        self,
        *,
        name: str,
        slug: str | None = None,
        owner_email: str,
        owner_display_name: str | None = None,
        owner_external_issuer: str | None = None,
        owner_external_subject: str | None = None,
        actor_id: str | None = None,
        actor_role: str | None = None,
    ) -> ProvisionedTenant:
        """Create a tenant and its first owner in one transaction.

        The caller is responsible for having authorised the request; this
        method only validates input and guarantees atomicity.
        """
        name = (name or "").strip()
        if not name:
            raise ValidationError("A tenant name is required.")
        if len(name) > 255:
            raise ValidationError("Tenant name must be 255 characters or fewer.")

        resolved_slug = (slug or slugify(name)).strip().lower()
        if not _SLUG_RE.match(resolved_slug):
            raise ValidationError(
                "Tenant slug must be 2-64 characters of lowercase letters, digits "
                "and single hyphens, and must start and end with a letter or digit."
            )

        email = (owner_email or "").strip().lower()
        if not email or "@" not in email:
            raise ValidationError("A valid owner email address is required.")

        if self.find_by_slug(resolved_slug) is not None:
            raise ConflictError(f"A tenant with slug '{resolved_slug}' already exists.")

        tenant = models.Tenant(
            id=str(uuid.uuid4()), name=name, slug=resolved_slug, is_active=True
        )
        self.session.add(tenant)
        try:
            # Flush so the foreign key for the membership resolves within the
            # same transaction.
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError(
                f"A tenant with slug '{resolved_slug}' already exists."
            ) from exc

        owner = models.User(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            email=email,
            display_name=(owner_display_name or email.split("@")[0])[:255],
            role="owner",
            is_active=True,
            external_issuer=owner_external_issuer,
            external_subject=owner_external_subject,
        )
        self.session.add(owner)

        self._audit(
            tenant.id,
            AuditAction.TENANT_CREATED,
            actor_id=actor_id,
            resource_type="tenant",
            resource_id=tenant.id,
            detail={
                "slug": resolved_slug,
                "bootstrap": actor_id is None,
                "actor_role": actor_role,
            },
        )
        self._audit(
            tenant.id,
            AuditAction.MEMBERSHIP_CREATED,
            actor_id=actor_id,
            resource_type="membership",
            resource_id=owner.id,
            detail={"role": "owner", "email": email, "initial_owner": True},
        )

        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError(
                "That owner is already a member of this tenant."
            ) from exc

        logger.info("tenant_created", tenant_id=tenant.id, slug=resolved_slug)
        return ProvisionedTenant(tenant=tenant, owner=owner)

    def add_membership(
        self,
        tenant_id: str,
        *,
        email: str,
        role: str = "member",
        display_name: str | None = None,
        external_issuer: str | None = None,
        external_subject: str | None = None,
        actor_id: str | None = None,
    ) -> models.User:
        """Add a membership to an existing tenant. Idempotency is NOT assumed."""
        tenant = self.get_tenant(tenant_id)
        if not tenant.is_active:
            raise ConflictError("Cannot add memberships to an inactive tenant.")

        role = (role or "member").strip().lower()
        if role not in TENANT_ROLES:
            raise ValidationError(
                f"Role must be one of: {', '.join(TENANT_ROLES)}."
            )

        email = (email or "").strip().lower()
        if not email or "@" not in email:
            raise ValidationError("A valid email address is required.")

        existing = self.session.execute(
            select(models.User).where(
                models.User.tenant_id == tenant_id, models.User.email == email
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError("That email already has a membership in this tenant.")

        if external_subject:
            duplicate_subject = self.session.execute(
                select(models.User).where(
                    models.User.tenant_id == tenant_id,
                    models.User.external_issuer == external_issuer,
                    models.User.external_subject == external_subject,
                )
            ).scalar_one_or_none()
            if duplicate_subject is not None:
                raise ConflictError("That identity already has a membership in this tenant.")

        membership = models.User(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            email=email,
            display_name=(display_name or email.split("@")[0])[:255],
            role=role,
            is_active=True,
            external_issuer=external_issuer,
            external_subject=external_subject,
        )
        self.session.add(membership)
        self._audit(
            tenant_id,
            AuditAction.MEMBERSHIP_CREATED,
            actor_id=actor_id,
            resource_type="membership",
            resource_id=membership.id,
            detail={"role": role, "email": email},
        )
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("That membership already exists.") from exc
        return membership

    def link_identity(
        self,
        tenant_id: str,
        membership_id: str,
        *,
        issuer: str,
        subject: str,
        actor_id: str | None = None,
    ) -> models.User:
        """Bind a provider subject to an existing membership.

        Separate from creation so an administrator can pre-invite an email and
        the identity is attached on first successful login.
        """
        membership = self.session.execute(
            select(models.User).where(
                models.User.id == membership_id, models.User.tenant_id == tenant_id
            )
        ).scalar_one_or_none()
        if membership is None:
            raise NotFoundError("Membership not found.")

        clash = self.session.execute(
            select(models.User).where(
                models.User.tenant_id == tenant_id,
                models.User.external_issuer == issuer,
                models.User.external_subject == subject,
                models.User.id != membership_id,
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise ConflictError("That identity is already linked to another membership.")

        membership.external_issuer = issuer
        membership.external_subject = subject
        self._audit(
            tenant_id,
            AuditAction.MEMBERSHIP_UPDATED,
            actor_id=actor_id,
            resource_type="membership",
            resource_id=membership.id,
            detail={"identity_linked": True},
        )
        self.session.flush()
        return membership

    def set_membership_active(
        self,
        tenant_id: str,
        membership_id: str,
        *,
        active: bool,
        actor_id: str | None = None,
    ) -> models.User:
        """Enable or revoke a membership (revocation is a soft disable)."""
        membership = self.session.execute(
            select(models.User).where(
                models.User.id == membership_id, models.User.tenant_id == tenant_id
            )
        ).scalar_one_or_none()
        if membership is None:
            raise NotFoundError("Membership not found.")

        if not active and membership.role == "owner":
            remaining = self.session.query(models.User).filter(
                models.User.tenant_id == tenant_id,
                models.User.role == "owner",
                models.User.is_active.is_(True),
                models.User.id != membership_id,
            ).count()
            if remaining == 0:
                raise ConflictError(
                    "Cannot revoke the last owner; promote another member first."
                )

        membership.is_active = active
        self._audit(
            tenant_id,
            AuditAction.MEMBERSHIP_REVOKED if not active else AuditAction.MEMBERSHIP_UPDATED,
            actor_id=actor_id,
            resource_type="membership",
            resource_id=membership.id,
            detail={"active": active},
        )
        self.session.flush()
        return membership

    # -- self-scoped reads ------------------------------------------------

    def memberships_for_subject(self, issuer: str, subject: str) -> list[models.User]:
        """Active memberships held by one verified provider subject.

        This is the *self-scoped* read: it is the only membership query that is
        not an administrative action, and it takes its filter from verified
        token claims rather than from anything the caller supplies.  A caller
        can therefore only ever learn about their own memberships, and only
        within active tenants — the same rule ``app.api.deps`` applies when it
        resolves a principal.

        The result is what the frontend is allowed to offer as a tenant choice.
        Selecting one is still re-validated server-side on every request.
        """
        stmt = (
            select(models.User)
            .join(models.Tenant, models.Tenant.id == models.User.tenant_id)
            .where(
                models.User.external_issuer == issuer,
                models.User.external_subject == subject,
                models.User.is_active.is_(True),
                models.Tenant.is_active.is_(True),
            )
            .order_by(models.User.created_at)
        )
        return list(self.session.execute(stmt).scalars().all())

    # -- bootstrap -------------------------------------------------------

    def bootstrap_required(self) -> bool:
        """True when no tenant exists yet — the platform has not been set up."""
        return self.session.query(models.Tenant).count() == 0

    def assert_bootstrap_authorised(self, token: str | None, configured_token: str | None) -> None:
        """Guard the first-tenant path.

        Bootstrapping is only reachable when no tenant exists AND the caller
        presents the configured bootstrap token.  Without a configured token
        the path is closed entirely.
        """
        if not configured_token:
            raise AuthorizationError(
                "Bootstrap provisioning is disabled. Configure "
                "HUMISENSE_BOOTSTRAP_TOKEN to enable initial setup."
            )
        if not token or not secrets.compare_digest(token, configured_token):
            raise AuthenticationError("A valid bootstrap token is required.")
