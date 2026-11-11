"""milestone 0: tenant provisioning, membership identity, referential integrity

Revision ID: a1f0c2d4e5b6
Revises: 94473a85bf00
Create Date: 2026-11-11

What this migration does, in order
----------------------------------
1. Adds identity columns to ``users`` so a row can bind to an OIDC subject.
2. **Backfills a ``tenants`` row for every ``tenant_id`` that already appears in
   tenant-scoped data but has no ``tenants`` row.** Without this, step 3 would
   fail on any existing deployment, because those rows currently violate the
   foreign key they are about to gain.
3. Adds the missing ``tenant_id -> tenants.id`` foreign keys.
4. Adds the unique constraint and index that make subject lookups efficient.

Step 2 is the fix for the audit's critical defect. It preserves every existing
record: nothing is deleted, and the backfilled tenants are named after the id
they were derived from so they are obvious to an administrator.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "a1f0c2d4e5b6"
down_revision = "94473a85bf00"
branch_labels = None
depends_on = None


# Tables that carry tenant_id.  Every one is backfilled before gaining an FK.
_TENANT_SCOPED_TABLES = (
    "connections",
    "credentials",
    "connection_resources",
    "sync_configs",
    "sync_checkpoints",
    "sync_runs",
    "dead_letters",
    "event_outbox",
    "integration_assessments",
    "custom_connector_definitions",
    "audit_logs",
    "webhook_deliveries",
    "users",
)

# Tables that gain a tenant foreign key in this migration.  ``connections`` and
# ``users`` already had one.
_TABLES_GAINING_FK = (
    "credentials",
    "connection_resources",
    "sync_configs",
    "sync_checkpoints",
    "sync_runs",
    "dead_letters",
    "event_outbox",
    "integration_assessments",
    "custom_connector_definitions",
    "audit_logs",
    "webhook_deliveries",
)

_FK_NAME = "fk_%(table)s_tenant"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # --- 1. identity columns on users ------------------------------------
    user_columns = {c["name"] for c in inspector.get_columns("users")}
    if "external_issuer" not in user_columns:
        op.add_column("users", sa.Column("external_issuer", sa.String(512), nullable=True))
    if "external_subject" not in user_columns:
        op.add_column("users", sa.Column("external_subject", sa.String(255), nullable=True))
    if "last_seen_at" not in user_columns:
        op.add_column("users", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))

    # --- 2. backfill orphan tenants --------------------------------------
    # Collect every distinct tenant_id present in tenant-scoped data.
    referenced: set[str] = set()
    for table in _TENANT_SCOPED_TABLES:
        if table not in existing_tables:
            continue
        rows = bind.execute(sa.text(f"SELECT DISTINCT tenant_id FROM {table}")).fetchall()
        referenced.update(str(row[0]) for row in rows if row[0] is not None)

    known = {
        str(row[0])
        for row in bind.execute(sa.text("SELECT id FROM tenants")).fetchall()
    }
    orphans = sorted(referenced - known)

    for tenant_id in orphans:
        # Derive a slug that is valid and obviously backfilled.
        slug_base = f"recovered-{tenant_id}"[:48]
        slug = slug_base
        # Guard against a slug collision with an existing tenant.
        suffix = 0
        while bind.execute(
            sa.text("SELECT 1 FROM tenants WHERE slug = :slug"), {"slug": slug}
        ).fetchone():
            suffix += 1
            slug = f"{slug_base}-{suffix}"[:63]
        bind.execute(
            sa.text(
                "INSERT INTO tenants (id, name, slug, created_at, is_active) "
                "VALUES (:id, :name, :slug, CURRENT_TIMESTAMP, :is_active)"
            ),
            {
                "id": tenant_id,
                "name": f"Recovered organization ({tenant_id})"[:255],
                "slug": slug,
                "is_active": True,
            },
        )

    # --- 3. foreign keys -------------------------------------------------
    for table in _TABLES_GAINING_FK:
        if table not in existing_tables:
            continue
        already = {fk["name"] for fk in inspector.get_foreign_keys(table)}
        fk_name = f"fk_{table}_tenant"
        if fk_name in already:
            continue
        with op.batch_alter_table(table) as batch:
            batch.create_foreign_key(
                fk_name, "tenants", ["tenant_id"], ["id"], ondelete="CASCADE"
            )

    # --- 4. subject uniqueness + lookup index ----------------------------
    # SQLite cannot add a constraint to an existing table, so a unique index is
    # used instead; PostgreSQL gets the same index, which enforces the same rule.
    index_names = {ix["name"] for ix in inspector.get_indexes("users")}
    if "uq_user_subject_tenant" not in index_names:
        op.create_index(
            "uq_user_subject_tenant",
            "users",
            ["external_issuer", "external_subject", "tenant_id"],
            unique=True,
        )
    if "ix_users_subject" not in index_names:
        op.create_index(
            "ix_users_subject", "users", ["external_issuer", "external_subject"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    index_names = {ix["name"] for ix in inspector.get_indexes("users")}
    if "ix_users_subject" in index_names:
        op.drop_index("ix_users_subject", table_name="users")
    if "uq_user_subject_tenant" in index_names:
        op.drop_index("uq_user_subject_tenant", table_name="users")

    for table in _TABLES_GAINING_FK:
        fks = {fk["name"] for fk in inspector.get_foreign_keys(table)}
        fk_name = f"fk_{table}_tenant"
        if fk_name in fks:
            with op.batch_alter_table(table) as batch:
                batch.drop_constraint(fk_name, type_="foreignkey")

    user_columns = {c["name"] for c in inspector.get_columns("users")}
    for column in ("last_seen_at", "external_subject", "external_issuer"):
        if column in user_columns:
            op.drop_column("users", column)

    # Backfilled tenants are intentionally NOT deleted on downgrade: they may
    # now be referenced by data that predates this migration, and deleting them
    # would cascade into that data. Removal is a manual, reviewed operation.
