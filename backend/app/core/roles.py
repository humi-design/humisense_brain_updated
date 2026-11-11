"""Tenant roles — the single source of truth.

Imported by both the provisioning service (to validate input) and the API
authorization layer (to check the resolved principal).  Keeping one definition
prevents the two from drifting apart.
"""

from __future__ import annotations

TENANT_ROLES = ("owner", "admin", "member", "viewer")
ADMIN_ROLES = ("owner", "admin")
