"""SQLAlchemy ORM models for Layer 1.

Every tenant-owned table carries a ``tenant_id`` column and every query in the
service layer filters on it.  On PostgreSQL the models also declare
row-level-security policies (see ``app/db/rls.py``) so that a coding mistake in
one service cannot leak another tenant's rows.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="member")  # owner|admin|member|viewer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_user_tenant_email"),)


class ConnectorRegistration(Base):
    """Registry table: which connector definitions are available to a tenant."""

    __tablename__ = "connector_registrations"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)  # connector_id
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), default="0.1.0")
    implementation_state: Mapped[str] = mapped_column(String(32), default="PLANNED")
    definition: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_installable: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Connection(Base):
    """A tenant-scoped connection to a provider."""

    __tablename__ = "connections"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    connector_id: Mapped[str] = mapped_column(
        ForeignKey("connector_registrations.id"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_identifier: Mapped[str | None] = mapped_column(String(255))
    resource_identifier: Mapped[str | None] = mapped_column(String(255))
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    granted_scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="configured", index=True)
    health_status: Mapped[str] = mapped_column(String(32), default="unknown")
    health_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    health_latency_ms: Mapped[float | None] = mapped_column(Float)
    health_message: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_successful_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    credential: Mapped[Credential | None] = relationship(
        back_populates="connection", uselist=False, cascade="all, delete-orphan"
    )
    resources: Mapped[list[ConnectionResource]] = relationship(
        back_populates="connection", cascade="all, delete-orphan"
    )
    sync_config: Mapped[SyncConfig | None] = relationship(
        back_populates="connection", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_connections_tenant_status", "tenant_id", "status"),
        UniqueConstraint("tenant_id", "provider", "display_name", name="uq_connection_name"),
    )


class Credential(Base):
    """Encrypted credential blob.  Plaintext never reaches this table."""

    __tablename__ = "credentials"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("connections.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    encrypted_payload: Mapped[str] = mapped_column(Text, nullable=False)
    nonce: Mapped[str] = mapped_column(String(64), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(32), default="AES-256-GCM")
    key_version: Mapped[int] = mapped_column(Integer, default=1)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    connection: Mapped[Connection] = relationship(back_populates="credential")


class ConnectionResource(Base):
    """A resource (repo/channel/table) the user authorised for a connection."""

    __tablename__ = "connection_resources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("connections.id", ondelete="CASCADE"), index=True, nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(512), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(String(512))
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False)
    read_only: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    connection: Mapped[Connection] = relationship(back_populates="resources")

    __table_args__ = (
        UniqueConstraint("connection_id", "external_id", name="uq_conn_resource"),
    )


class SyncConfig(Base):
    __tablename__ = "sync_configs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("connections.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    mode: Mapped[str] = mapped_column(String(32), default="incremental")
    schedule_cron: Mapped[str | None] = mapped_column(String(64))
    page_size: Mapped[int] = mapped_column(Integer, default=100)
    batch_size: Mapped[int] = mapped_column(Integer, default=500)
    lookback_seconds: Mapped[int | None] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    max_retries: Mapped[int] = mapped_column(Integer, default=5)
    write_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    connection: Mapped[Connection] = relationship(back_populates="sync_config")


class SyncCheckpointRow(Base):
    __tablename__ = "sync_checkpoints"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("connections.id", ondelete="CASCADE"), index=True, nullable=False
    )
    resource_id: Mapped[str] = mapped_column(String(512), nullable=False)
    cursor: Mapped[str | None] = mapped_column(Text)
    page_token: Mapped[str | None] = mapped_column(Text)
    watermark: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    records_seen: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint("connection_id", "resource_id", name="uq_checkpoint_resource"),
    )


class SyncRunRow(Base):
    __tablename__ = "sync_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("connections.id", ondelete="CASCADE"), index=True, nullable=False
    )
    resource_id: Mapped[str | None] = mapped_column(String(512))
    mode: Mapped[str] = mapped_column(String(32), default="incremental")
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    records_fetched: Mapped[int] = mapped_column(Integer, default=0)
    records_written: Mapped[int] = mapped_column(Integer, default=0)
    records_skipped: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeadLetterRow(Base):
    """Records that could not be processed, kept for manual resynchronisation."""

    __tablename__ = "dead_letters"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    sync_run_id: Mapped[str | None] = mapped_column(String(64))
    resource_id: Mapped[str | None] = mapped_column(String(512))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EventOutbox(Base):
    """Transactional outbox for the Layer 1 -> Layer 2 event contract."""

    __tablename__ = "event_outbox"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), default="1.0")
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IntegrationAssessmentRow(Base):
    __tablename__ = "integration_assessments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    application_name: Mapped[str] = mapped_column(String(255), nullable=False)
    vendor: Mapped[str | None] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(64), default="generic")
    discovery_source: Mapped[str] = mapped_column(String(64), nullable=False)
    integration_class: Mapped[str] = mapped_column(String(64), default="DISCOVERY_PENDING", index=True)
    available_integration_method: Mapped[str | None] = mapped_column(String(128))
    authentication_requirements: Mapped[list[str]] = mapped_column(JSON, default=list)
    data_access_feasibility: Mapped[str] = mapped_column(String(32), default="unknown")
    read_capability: Mapped[bool] = mapped_column(Boolean, default=False)
    write_capability: Mapped[bool] = mapped_column(Boolean, default=False)
    required_permissions: Mapped[list[str]] = mapped_column(JSON, default=list)
    integration_risks: Mapped[list[str]] = mapped_column(JSON, default=list)
    implementation_estimate_days: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), default="PLANNED")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CustomConnectorDefinitionRow(Base):
    """Versioned custom connector definition built in the Universal Studio."""

    __tablename__ = "custom_connector_definitions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    adapter_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    definition: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    review_status: Mapped[str] = mapped_column(String(32), default="draft")
    # draft | pending_review | approved | rejected | published
    validation_report: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (UniqueConstraint("tenant_id", "name", "version", name="uq_custom_def_version"),)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class WebhookSignatureRecord(Base):
    """Tracks webhook deliveries for replay protection (idempotency)."""

    __tablename__ = "webhook_deliveries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    delivery_id: Mapped[str] = mapped_column(String(255), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("connection_id", "delivery_id", name="uq_webhook_delivery"),
    )
