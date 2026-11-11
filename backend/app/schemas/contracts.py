"""Standard connector contracts.

These Pydantic models are the single source of truth shared by the registry,
the connection service, the sync engine and the API layer.  Every connector
implementation exchanges data through these types only - arbitrary connector
code never sees raw ORM objects.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ImplementationState(str, Enum):
    """Honest maturity label for every capability."""

    PLANNED = "PLANNED"
    SCAFFOLDED = "SCAFFOLDED"
    IMPLEMENTED = "IMPLEMENTED"
    TESTED = "TESTED"
    INTEGRATION_VERIFIED = "INTEGRATION_VERIFIED"
    PRODUCTION_READY = "PRODUCTION_READY"


class ConnectorCategory(str, Enum):
    COMMUNICATION = "communication"
    EMAIL_CALENDAR = "email_calendar"
    MEETINGS = "meetings"
    DOCUMENTS = "documents"
    CRM = "crm"
    ERP_FINANCE = "erp_finance"
    PROJECT_MANAGEMENT = "project_management"
    MANUFACTURING_INDUSTRIAL = "manufacturing_industrial"
    HR = "hr"
    GENERIC = "generic"


class AuthType(str, Enum):
    OAUTH2_AUTHORIZATION_CODE = "oauth2_authorization_code"
    OAUTH2_CLIENT_CREDENTIALS = "oauth2_client_credentials"
    API_KEY = "api_key"
    BEARER_TOKEN = "bearer_token"
    PERSONAL_ACCESS_TOKEN = "personal_access_token"
    BASIC = "basic"
    SERVICE_ACCOUNT_JSON = "service_account_json"
    CLIENT_CERTIFICATE = "client_certificate"
    DATABASE_CREDENTIALS = "database_credentials"
    SFTP_KEY = "sftp_key"
    WEBHOOK_SECRET = "webhook_secret"
    NONE = "none"


class Capability(str, Enum):
    READ = "read"
    WRITE = "write"
    WEBHOOK = "webhook"
    INCREMENTAL = "incremental"
    SCHEMA_DISCOVERY = "schema_discovery"
    BINARY_FETCH = "binary_fetch"
    QUERY = "query"
    STREAM = "stream"


class ConnectionStatus(str, Enum):
    """Full lifecycle of a connector instance (registry status model)."""

    CATALOGUE_AVAILABLE = "catalogue_available"
    INSTALLABLE = "installable"
    CONFIGURED = "configured"
    AUTHENTICATED = "authenticated"
    CONNECTED = "connected"
    SYNCHRONIZING = "synchronizing"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"
    REVOKED = "revoked"
    FAILED = "failed"


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class SyncMode(str, Enum):
    FULL = "full"
    INCREMENTAL = "incremental"
    WEBHOOK = "webhook"


class SyncRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"
    CANCELLED = "cancelled"


class IntegrationAssessmentClass(str, Enum):
    PREBUILT_CONNECTOR_AVAILABLE = "PREBUILT_CONNECTOR_AVAILABLE"
    UNIVERSAL_ADAPTER_AVAILABLE = "UNIVERSAL_ADAPTER_AVAILABLE"
    CUSTOM_CONNECTOR_REQUIRED = "CUSTOM_CONNECTOR_REQUIRED"
    VENDOR_ASSISTANCE_REQUIRED = "VENDOR_ASSISTANCE_REQUIRED"
    MANUAL_IMPORT_AVAILABLE = "MANUAL_IMPORT_AVAILABLE"
    INTEGRATION_NOT_FEASIBLE = "INTEGRATION_NOT_FEASIBLE"
    DISCOVERY_PENDING = "DISCOVERY_PENDING"


class DiscoverySource(str, Enum):
    CUSTOMER_INVENTORY = "customer_inventory"
    ENTRA_ID_CATALOGUE = "entra_id_catalogue"
    CLOUD_APP_INVENTORY = "cloud_app_inventory"
    CMDB = "cmdb"
    API_DOCUMENTATION = "api_documentation"
    OPENAPI_SPEC = "openapi_spec"
    DATABASE_SCHEMA = "database_schema"
    VENDOR_DOCUMENTATION = "vendor_documentation"
    NETWORK_INVENTORY = "network_inventory"
    MANUAL = "manual"


class AdapterKind(str, Enum):
    REST = "rest"
    GRAPHQL = "graphql"
    SQL = "sql"
    WEBHOOK = "webhook"
    FILE = "file"
    SFTP = "sftp"
    OPCUA = "opcua"
    MQTT = "mqtt"
    INDUSTRIAL_GATEWAY = "industrial_gateway"


class AssessmentFeasibility(str, Enum):
    FEASIBLE = "feasible"
    FEASIBLE_WITH_CONDITIONS = "feasible_with_conditions"
    NOT_FEASIBLE = "not_feasible"
    UNKNOWN = "unknown"


class AuditAction(str, Enum):
    CONNECTION_CREATED = "connection_created"
    CONNECTION_UPDATED = "connection_updated"
    CONNECTION_AUTHENTICATED = "connection_authenticated"
    CONNECTION_TESTED = "connection_tested"
    CONNECTION_REVOKED = "connection_revoked"
    CONNECTION_DELETED = "connection_deleted"
    CREDENTIAL_ROTATED = "credential_rotated"
    SYNC_STARTED = "sync_started"
    SYNC_SUCCEEDED = "sync_succeeded"
    SYNC_FAILED = "sync_failed"
    RESOURCE_SELECTED = "resource_selected"
    TENANT_ISOLATION_VIOLATION = "tenant_isolation_violation"
    EGRESS_BLOCKED = "egress_blocked"
    WEBHOOK_REJECTED = "webhook_rejected"
    # --- Milestone 0: identity and provisioning -------------------------
    TENANT_CREATED = "tenant_created"
    TENANT_UPDATED = "tenant_updated"
    MEMBERSHIP_CREATED = "membership_created"
    MEMBERSHIP_UPDATED = "membership_updated"
    MEMBERSHIP_REVOKED = "membership_revoked"
    IDENTITY_AUTHENTICATED = "identity_authenticated"
    AUTHENTICATION_FAILED = "authentication_failed"


# ---------------------------------------------------------------------------
# Core contracts
# ---------------------------------------------------------------------------


class CredentialReference(BaseModel):
    """Opaque handle to a stored secret. Never contains the secret itself."""

    model_config = ConfigDict(extra="forbid")

    reference_id: str
    tenant_id: str
    connection_id: str
    key_version: int = 1
    algorithm: str = "AES-256-GCM"
    created_at: datetime = Field(default_factory=utcnow)
    rotated_at: datetime | None = None
    expires_at: datetime | None = None

    def is_expired(self, *, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        return (now or utcnow()) >= self.expires_at


class ConnectionConfiguration(BaseModel):
    """Non-secret connection settings supplied by the operator."""

    model_config = ConfigDict(extra="forbid")

    base_url: str | None = None
    host: str | None = None
    port: int | None = None
    database: str | None = None
    region: str | None = None
    tenant_hint: str | None = None
    resource: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("port")
    @classmethod
    def _valid_port(cls, value: int | None) -> int | None:
        if value is not None and not (1 <= value <= 65535):
            raise ValueError("port must be between 1 and 65535")
        return value


class ConnectorResource(BaseModel):
    """A selectable resource exposed by a connector (e.g. a repo, a channel)."""

    model_config = ConfigDict(extra="forbid")

    external_id: str
    name: str
    resource_type: str
    parent_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    selectable: bool = True
    read_only: bool = True


class ConnectorCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability: Capability
    resources: list[str] = Field(default_factory=list)
    notes: str | None = None
    implementation_state: ImplementationState = ImplementationState.PLANNED


class SyncConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: SyncMode = SyncMode.INCREMENTAL
    schedule_cron: str | None = None
    page_size: int = Field(default=100, ge=1, le=10_000)
    batch_size: int = Field(default=500, ge=1, le=100_000)
    resource_ids: list[str] = Field(default_factory=list)
    lookback_seconds: int | None = Field(default=None, ge=0)
    enabled: bool = True
    max_retries: int = Field(default=5, ge=0, le=25)
    write_enabled: bool = False


class SyncCheckpoint(BaseModel):
    """Durable cursor so a failed sync can resume exactly where it stopped."""

    model_config = ConfigDict(extra="forbid")

    connection_id: str
    resource_id: str
    cursor: str | None = None
    watermark: datetime | None = None
    page_token: str | None = None
    records_seen: int = 0
    updated_at: datetime = Field(default_factory=utcnow)


class ConnectorHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: HealthStatus = HealthStatus.UNKNOWN
    checked_at: datetime = Field(default_factory=utcnow)
    latency_ms: float | None = None
    message: str | None = None
    consecutive_failures: int = 0


class ConnectorDefinition(BaseModel):
    """Static description of a connector type (registry entry)."""

    model_config = ConfigDict(extra="forbid")

    connector_id: str
    provider: str
    display_name: str
    category: ConnectorCategory
    description: str
    version: str = "0.1.0"
    auth_types: list[AuthType]
    capabilities: list[ConnectorCapability] = Field(default_factory=list)
    required_scopes: list[str] = Field(default_factory=list)
    optional_scopes: list[str] = Field(default_factory=list)
    supported_resources: list[str] = Field(default_factory=list)
    configuration_schema: dict[str, Any] = Field(default_factory=dict)
    documentation_url: str | None = None
    implementation_state: ImplementationState = ImplementationState.PLANNED
    supports_webhooks: bool = False
    supports_incremental: bool = False
    is_read_only: bool = True
    requires_on_premise: bool = False
    required_license: str | None = None
    rate_limit_notes: str | None = None
    known_limitations: list[str] = Field(default_factory=list)


class ConnectorInstance(BaseModel):
    """A concrete, tenant-scoped connection to a provider."""

    model_config = ConfigDict(extra="forbid")

    connection_id: str
    tenant_id: str
    connector_id: str
    provider: str
    display_name: str
    account_identifier: str | None = None
    resource_identifier: str | None = None
    credential_reference: CredentialReference | None = None
    granted_scopes: list[str] = Field(default_factory=list)
    status: ConnectionStatus = ConnectionStatus.CONFIGURED
    health: ConnectorHealth = Field(default_factory=ConnectorHealth)
    last_successful_sync: datetime | None = None
    last_error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class SyncRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    connection_id: str
    tenant_id: str
    resource_id: str | None = None
    mode: SyncMode = SyncMode.INCREMENTAL
    status: SyncRunStatus = SyncRunStatus.PENDING
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    records_fetched: int = 0
    records_written: int = 0
    records_skipped: int = 0
    error: str | None = None
    attempt: int = 1


class IntegrationAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment_id: str
    tenant_id: str
    application_name: str
    vendor: str | None = None
    category: ConnectorCategory = ConnectorCategory.GENERIC
    discovery_source: DiscoverySource
    integration_class: IntegrationAssessmentClass = IntegrationAssessmentClass.DISCOVERY_PENDING
    available_integration_method: str | None = None
    authentication_requirements: list[str] = Field(default_factory=list)
    data_access_feasibility: AssessmentFeasibility = AssessmentFeasibility.UNKNOWN
    read_capability: bool = False
    write_capability: bool = False
    required_permissions: list[str] = Field(default_factory=list)
    integration_risks: list[str] = Field(default_factory=list)
    implementation_estimate_days: float | None = None
    status: ImplementationState = ImplementationState.PLANNED
    notes: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class NormalizedRecord(BaseModel):
    """Source record plus provenance. Layer 1 does not interpret business meaning."""

    model_config = ConfigDict(extra="forbid")

    source_record_id: str
    resource_id: str
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime = Field(default_factory=utcnow)
    source_updated_at: datetime | None = None
    content_hash: str | None = None


class FetchPage(BaseModel):
    """One page of results plus the cursor needed to continue."""

    model_config = ConfigDict(extra="forbid")

    records: list[NormalizedRecord] = Field(default_factory=list)
    next_cursor: str | None = None
    next_page_token: str | None = None
    has_more: bool = False
    watermark: datetime | None = None
    fetched_at: datetime = Field(default_factory=utcnow)


class EventEnvelope(BaseModel):
    """Documented Layer 1 -> Layer 2 contract.

    Layer 1 publishes raw, provenance-preserving records.  Interpretation,
    task extraction and reasoning belong to Layer 2.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: str
    schema_version: str = "1.0"
    tenant_id: str
    connection_id: str
    connector_id: str
    resource_id: str | None = None
    occurred_at: datetime = Field(default_factory=utcnow)
    idempotency_key: str
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_tenant(self) -> EventEnvelope:
        if not self.tenant_id:
            raise ValueError("EventEnvelope requires a tenant_id")
        return self


class ConnectorTestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool
    message: str
    latency_ms: float | None = None
    account_identifier: str | None = None
    granted_scopes: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PaginationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: Literal["cursor", "page", "offset", "link_header", "none"] = "page"
    page_param: str = "page"
    size_param: str = "per_page"
    cursor_param: str = "cursor"
    cursor_json_path: str | None = None
    items_json_path: str | None = None
    total_json_path: str | None = None
