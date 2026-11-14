"""Request/response schemas for the Layer 1 API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.contracts import (
    AdapterKind,
    AuthType,
    ConnectionStatus,
    ConnectorCategory,
    DiscoverySource,
    ImplementationState,
    IntegrationAssessmentClass,
    SyncConfiguration,
    SyncMode,
)


class ConnectorDefinitionOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    connector_id: str
    provider: str
    display_name: str
    category: ConnectorCategory
    description: str
    version: str
    auth_types: list[AuthType]
    capabilities: list[dict[str, Any]]
    required_scopes: list[str]
    supported_resources: list[str]
    implementation_state: ImplementationState
    is_installable: bool
    supports_webhooks: bool
    supports_incremental: bool
    is_read_only: bool
    requires_on_premise: bool
    required_license: str | None = None
    known_limitations: list[str] = Field(default_factory=list)
    documentation_url: str | None = None


class ConnectionCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_id: str
    display_name: str = Field(min_length=1, max_length=255)
    configuration: dict[str, Any] = Field(default_factory=dict)
    credentials: dict[str, Any] = Field(default_factory=dict)
    granted_scopes: list[str] = Field(default_factory=list)


class CredentialRotateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credentials: dict[str, Any]


class ResourceSelectionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_ids: list[str]


class SyncConfigureIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: SyncMode = SyncMode.INCREMENTAL
    schedule_cron: str | None = None
    page_size: int = Field(default=100, ge=1, le=10_000)
    batch_size: int = Field(default=500, ge=1, le=100_000)
    lookback_seconds: int | None = Field(default=None, ge=0)
    enabled: bool = True
    max_retries: int = Field(default=5, ge=0, le=25)
    write_enabled: bool = False

    def to_contract(self) -> SyncConfiguration:
        return SyncConfiguration(**self.model_dump())


class ConnectionOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    connection_id: str
    connector_id: str
    provider: str
    display_name: str
    account_identifier: str | None = None
    status: ConnectionStatus
    health_status: str
    health_checked_at: datetime | None = None
    health_latency_ms: float | None = None
    health_message: str | None = None
    granted_scopes: list[str] = Field(default_factory=list)
    last_successful_sync: datetime | None = None
    last_error: str | None = None
    credential_reference_id: str | None = None
    credential_rotated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ConnectionResourceOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    external_id: str
    name: str
    resource_type: str
    parent_id: str | None = None
    is_selected: bool
    read_only: bool
    metadata: dict[str, Any] = Field(default_factory=dict)


class TestConnectionOut(BaseModel):
    success: bool
    message: str
    latency_ms: float | None = None
    account_identifier: str | None = None
    granted_scopes: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class AssessmentOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    assessment_id: str
    application_name: str
    vendor: str | None = None
    category: ConnectorCategory
    discovery_source: DiscoverySource
    integration_class: IntegrationAssessmentClass
    available_integration_method: str | None = None
    authentication_requirements: list[str] = Field(default_factory=list)
    data_access_feasibility: str
    read_capability: bool
    write_capability: bool
    required_permissions: list[str] = Field(default_factory=list)
    integration_risks: list[str] = Field(default_factory=list)
    implementation_estimate_days: float | None = None
    status: ImplementationState
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class AssessmentCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_name: str = Field(min_length=1, max_length=255)
    vendor: str | None = None
    category_hint: str | None = None
    discovery_source: DiscoverySource = DiscoverySource.MANUAL
    has_api_docs: bool = False
    openapi_available: bool = False
    database_reachable: bool = False
    on_premise_only: bool = False
    notes: str | None = None


class AssessmentUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    integration_class: IntegrationAssessmentClass | None = None
    available_integration_method: str | None = None
    data_access_feasibility: str | None = None
    read_capability: bool | None = None
    write_capability: bool | None = None
    required_permissions: list[str] | None = None
    integration_risks: list[str] | None = None
    implementation_estimate_days: float | None = None
    status: ImplementationState | None = None
    notes: str | None = None


class CustomDefinitionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    adapter_kind: AdapterKind
    definition: dict[str, Any]
    generated_by_ai: bool = False


class CustomDefinitionOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    adapter_kind: str
    version: int
    definition: dict[str, Any]
    review_status: str
    validation_report: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class TransitionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str


class SyncRunOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run_id: str
    connection_id: str
    resource_id: str | None = None
    mode: str
    status: str
    records_fetched: int
    records_written: int
    records_skipped: int
    error: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


class DeadLetterOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    connection_id: str
    resource_id: str | None = None
    reason: str
    payload: dict[str, Any]
    resolved: bool
    created_at: datetime


class AuditLogOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    action: str
    resource_type: str
    resource_id: str | None = None
    actor_id: str | None = None
    detail: dict[str, Any]
    created_at: datetime


class TenantCreateIn(BaseModel):
    """Provision a tenant and its first owner in one operation."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(default=None, max_length=64)
    owner_email: str = Field(min_length=3, max_length=320)
    owner_display_name: str | None = Field(default=None, max_length=255)
    # Identity linkage is optional: an administrator may invite by email and let
    # the subject attach on first login.
    owner_external_subject: str | None = Field(default=None, max_length=255)


class TenantOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tenant_id: str
    name: str
    slug: str
    is_active: bool
    created_at: datetime


class MembershipCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    role: str = Field(default="member")
    display_name: str | None = Field(default=None, max_length=255)
    external_subject: str | None = Field(default=None, max_length=255)


class MembershipOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    membership_id: str
    tenant_id: str
    email: str
    display_name: str
    role: str
    is_active: bool
    identity_linked: bool
    created_at: datetime


class SelfMembershipOut(BaseModel):
    """One of the caller's own memberships.

    Deliberately narrower than :class:`MembershipOut`: it exposes only what the
    frontend needs to offer a tenant choice, and no other member's data.  There
    is no ``email``/``display_name`` field because this is a self-scoped read,
    not an administrative one.
    """

    model_config = ConfigDict(extra="ignore")

    tenant_id: str
    tenant_name: str
    tenant_slug: str | None
    role: str


class MembershipActiveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: bool


class LinkIdentityIn(BaseModel):
    """Bind a verified provider subject to an existing membership."""

    model_config = ConfigDict(extra="forbid")

    external_subject: str = Field(min_length=1, max_length=255)


class WhoAmIOut(BaseModel):
    """The server-resolved identity. Proof that headers are not trusted."""

    model_config = ConfigDict(extra="ignore")

    tenant_id: str
    user_id: str | None
    role: str
    subject: str | None
    source: str
    is_admin: bool
    auth_mode: str


class HealthOut(BaseModel):
    status: str
    version: str
    database: str
    connectors_registered: int
    connectors_installable: int


class EventContractOut(BaseModel):
    """Documents the Layer 1 -> Layer 2 event contract."""

    schema_version: str
    event_types: list[dict[str, Any]]
    delivery: dict[str, Any]
