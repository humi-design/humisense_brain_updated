"""Company Technology Discovery.

Identifies which applications an organisation uses and how Humisense could
integrate with each one.  Discovery is **authorised only**:

* Customer-provided application inventories (CSV/JSON/Excel).
* Microsoft Entra ID enterprise-application catalogue (customer-authorised
  Graph call, performed elsewhere - this module consumes the export).
* CMDB / IT asset inventories.
* OpenAPI specifications and API documentation.
* Database schemas and vendor documentation.

This module never performs network scanning, credential discovery or
application enumeration.  **Discovery is not authorisation**: an assessment
records feasibility, not access.  A separate, explicit connection is required
before any data is read.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.registry import registry
from app.core.errors import ValidationError
from app.db import models
from app.schemas.contracts import (
    AssessmentFeasibility,
    ConnectorCategory,
    DiscoverySource,
    ImplementationState,
    IntegrationAssessment,
    IntegrationAssessmentClass,
)

# Keyword -> category heuristics for inventory rows that do not declare one.
_CATEGORY_KEYWORDS: dict[ConnectorCategory, tuple[str, ...]] = {
    ConnectorCategory.CRM: ("salesforce", "hubspot", "crm", "dynamics", "pipedrive", "zoho crm"),
    ConnectorCategory.ERP_FINANCE: ("sap", "netsuite", "oracle", "odoo", "erpnext", "tally",
                                    "quickbooks", "xero", "sage", "business central"),
    ConnectorCategory.HR: ("workday", "successfactors", "bamboohr", "darwinbox", "zoho people", "hris"),
    ConnectorCategory.PROJECT_MANAGEMENT: ("jira", "confluence", "asana", "trello", "monday",
                                           "clickup", "linear", "github", "gitlab", "azure devops"),
    ConnectorCategory.MANUFACTURING_INDUSTRIAL: ("canary", "pi system", "aveva", "ignition",
                                                 "influx", "timescale", "wincc", "factorytalk",
                                                 "opcenter", "scada", "historian", "mes", "cmms", "qms"),
    ConnectorCategory.DOCUMENTS: ("drive", "sharepoint", "onedrive", "dropbox", "box"),
    ConnectorCategory.MEETINGS: ("zoom", "meet", "webex", "teams"),
    ConnectorCategory.EMAIL_CALENDAR: ("gmail", "outlook", "exchange", "imap", "calendar"),
    ConnectorCategory.COMMUNICATION: ("slack", "teams", "whatsapp", "telegram", "discord", "chat"),
}

# Provider keyword -> connector_id for prebuilt matching.
_PREBUILT_HINTS: dict[str, str] = {
    "github": "github", "gitlab": "gitlab", "azure devops": "azure_devops",
    "slack": "slack", "jira": "jira", "confluence": "confluence",
    "salesforce": "salesforce", "hubspot": "hubspot", "zoho crm": "zoho_crm",
    "pipedrive": "pipedrive", "freshsales": "freshsales",
    "sap": "sap", "netsuite": "oracle_netsuite", "odoo": "odoo", "erpnext": "erpnext",
    "tally": "tally", "quickbooks": "quickbooks", "xero": "xero", "sage": "sage",
    "workday": "workday", "bamboohr": "bamboohr", "darwinbox": "darwinbox",
    "asana": "asana", "trello": "trello", "monday": "monday", "clickup": "clickup",
    "linear": "linear", "zoom": "zoom", "webex": "webex",
    "gmail": "gmail", "outlook": "microsoft_graph_mail", "google drive": "google_drive",
    "sharepoint": "sharepoint", "onedrive": "onedrive", "dropbox": "dropbox", "box": "box",
    "canary": "canary_labs", "pi system": "aveva_pi", "ignition": "ignition",
    "influxdb": "influxdb", "timescaledb": "timescaledb", "wincc": "siemens_wincc",
    "factorytalk": "rockwell_factorytalk", "opcenter": "siemens_opcenter",
    "dynamics 365": "dynamics365_crm", "business central": "business_central",
}

# Categories where a universal SQL/REST adapter is usually the pragmatic route.
_ADAPTER_FRIENDLY = {
    ConnectorCategory.ERP_FINANCE,
    ConnectorCategory.MANUFACTURING_INDUSTRIAL,
    ConnectorCategory.HR,
}


class TechnologyDiscoveryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # -- inventory import -------------------------------------------------

    def import_inventory(
        self,
        tenant_id: str,
        *,
        content: bytes,
        filename: str,
        source: DiscoverySource = DiscoverySource.CUSTOMER_INVENTORY,
    ) -> list[models.IntegrationAssessmentRow]:
        rows = _parse_inventory(content, filename)
        if not rows:
            raise ValidationError("No applications were found in the supplied inventory.")
        created: list[models.IntegrationAssessmentRow] = []
        for row in rows:
            assessment = self.assess_application(
                tenant_id,
                application_name=str(row.get("name") or row.get("application") or "").strip(),
                vendor=(str(row.get("vendor")).strip() if row.get("vendor") else None),
                category_hint=row.get("category"),
                source=source,
                notes=row.get("notes"),
            )
            created.append(assessment)
        return created

    # -- assessment -------------------------------------------------------

    def assess_application(
        self,
        tenant_id: str,
        *,
        application_name: str,
        vendor: str | None = None,
        category_hint: str | None = None,
        source: DiscoverySource = DiscoverySource.MANUAL,
        has_api_docs: bool = False,
        openapi_available: bool = False,
        database_reachable: bool = False,
        on_premise_only: bool = False,
        notes: str | None = None,
    ) -> models.IntegrationAssessmentRow:
        if not application_name:
            raise ValidationError("application_name is required.")

        haystack = f"{application_name} {vendor or ''} {category_hint or ''}".lower()
        category = _detect_category(haystack, category_hint)
        connector_id = _match_prebuilt(haystack)

        integration_class, method, feasibility, estimate, risks, status_state = _classify(
            connector_id=connector_id,
            category=category,
            openapi_available=openapi_available,
            has_api_docs=has_api_docs,
            database_reachable=database_reachable,
            on_premise_only=on_premise_only,
        )

        read_capability = integration_class in {
            IntegrationAssessmentClass.PREBUILT_CONNECTOR_AVAILABLE,
            IntegrationAssessmentClass.UNIVERSAL_ADAPTER_AVAILABLE,
            IntegrationAssessmentClass.CUSTOM_CONNECTOR_REQUIRED,
            IntegrationAssessmentClass.MANUAL_IMPORT_AVAILABLE,
        }

        row = models.IntegrationAssessmentRow(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            application_name=application_name,
            vendor=vendor,
            category=category.value,
            discovery_source=source.value,
            integration_class=integration_class.value,
            available_integration_method=method,
            authentication_requirements=_auth_requirements(connector_id, integration_class),
            data_access_feasibility=feasibility.value,
            read_capability=read_capability,
            write_capability=False,
            required_permissions=_permissions(connector_id),
            integration_risks=risks,
            implementation_estimate_days=estimate,
            status=status_state.value,
            notes=notes,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def list_assessments(self, tenant_id: str) -> list[models.IntegrationAssessmentRow]:
        return list(
            self.session.execute(
                select(models.IntegrationAssessmentRow)
                .where(models.IntegrationAssessmentRow.tenant_id == tenant_id)
                .order_by(models.IntegrationAssessmentRow.created_at.desc())
            ).scalars().all()
        )

    def update_assessment(
        self, tenant_id: str, assessment_id: str, **fields: Any
    ) -> models.IntegrationAssessmentRow:
        row = self.session.execute(
            select(models.IntegrationAssessmentRow).where(
                models.IntegrationAssessmentRow.id == assessment_id,
                models.IntegrationAssessmentRow.tenant_id == tenant_id,
            )
        ).scalar_one_or_none()
        if row is None:
            from app.core.errors import NotFoundError

            raise NotFoundError("Assessment not found.")
        allowed = {
            "integration_class", "available_integration_method", "data_access_feasibility",
            "read_capability", "write_capability", "required_permissions",
            "integration_risks", "implementation_estimate_days", "status", "notes",
        }
        for key, value in fields.items():
            if key in allowed and value is not None:
                setattr(row, key, value)
        self.session.flush()
        return row

    def to_contract(self, row: models.IntegrationAssessmentRow) -> IntegrationAssessment:
        return IntegrationAssessment(
            assessment_id=row.id,
            tenant_id=row.tenant_id,
            application_name=row.application_name,
            vendor=row.vendor,
            category=ConnectorCategory(row.category),
            discovery_source=DiscoverySource(row.discovery_source),
            integration_class=IntegrationAssessmentClass(row.integration_class),
            available_integration_method=row.available_integration_method,
            authentication_requirements=list(row.authentication_requirements or []),
            data_access_feasibility=AssessmentFeasibility(row.data_access_feasibility),
            read_capability=row.read_capability,
            write_capability=row.write_capability,
            required_permissions=list(row.required_permissions or []),
            integration_risks=list(row.integration_risks or []),
            implementation_estimate_days=row.implementation_estimate_days,
            status=ImplementationState(row.status),
            notes=row.notes,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------


def _detect_category(haystack: str, hint: str | None) -> ConnectorCategory:
    if hint:
        try:
            return ConnectorCategory(hint.lower())
        except ValueError:
            pass
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return category
    return ConnectorCategory.GENERIC


def _match_prebuilt(haystack: str) -> str | None:
    for hint, connector_id in _PREBUILT_HINTS.items():
        if hint in haystack:
            if registry.is_installable(connector_id):
                return connector_id
            # Catalogued but not installable yet - still a prebuilt target.
            try:
                registry.get_definition(connector_id)
                return connector_id
            except Exception:  # noqa: BLE001
                continue
    return None


def _classify(
    *,
    connector_id: str | None,
    category: ConnectorCategory,
    openapi_available: bool,
    has_api_docs: bool,
    database_reachable: bool,
    on_premise_only: bool,
) -> tuple[
    IntegrationAssessmentClass, str | None, AssessmentFeasibility, float | None,
    list[str], ImplementationState,
]:
    risks: list[str] = []
    status_state = ImplementationState.PLANNED
    if connector_id is not None:
        try:
            definition = registry.get_definition(connector_id)
            installable = registry.is_installable(connector_id)
        except Exception:  # noqa: BLE001
            definition, installable = None, False
        method = f"prebuilt:{connector_id}"
        if definition is not None:
            status_state = definition.implementation_state
            if definition.requires_on_premise:
                risks.append("On-premise deployment; network reachability and allowlisting required.")
            if definition.required_license:
                risks.append(f"Requires licence/permission: {definition.required_license}")
            risks.extend(definition.known_limitations)
        if not installable:
            risks.append(
                "Connector is catalogued but not yet installable; delivery is pending. "
                "Until it ships, a custom connector or universal adapter is required."
            )
        # A prebuilt connector is the intended integration route either way;
        # the implementation state (recorded in ``status``) carries the maturity.
        return (
            IntegrationAssessmentClass.PREBUILT_CONNECTOR_AVAILABLE,
            method,
            AssessmentFeasibility.FEASIBLE if installable
            else AssessmentFeasibility.FEASIBLE_WITH_CONDITIONS,
            1.0 if installable else 15.0,
            risks,
            status_state,
        )

    if openapi_available or has_api_docs:
        return (
            IntegrationAssessmentClass.UNIVERSAL_ADAPTER_AVAILABLE,
            "universal_rest",
            AssessmentFeasibility.FEASIBLE,
            2.0,
            risks,
            ImplementationState.IMPLEMENTED,
        )
    if database_reachable:
        risks.append("Direct database access must be read-only and network-restricted.")
        return (
            IntegrationAssessmentClass.UNIVERSAL_ADAPTER_AVAILABLE,
            "universal_sql",
            AssessmentFeasibility.FEASIBLE_WITH_CONDITIONS,
            3.0,
            risks,
            ImplementationState.IMPLEMENTED,
        )
    if category in _ADAPTER_FRIENDLY:
        risks.append("No documented API discovered; vendor assistance may be required.")
        return (
            IntegrationAssessmentClass.VENDOR_ASSISTANCE_REQUIRED,
            None,
            AssessmentFeasibility.FEASIBLE_WITH_CONDITIONS,
            20.0,
            risks,
            ImplementationState.PLANNED,
        )
    risks.append("No machine-readable interface identified. Manual import may be the only option.")
    return (
        IntegrationAssessmentClass.MANUAL_IMPORT_AVAILABLE,
        "universal_file",
        AssessmentFeasibility.FEASIBLE_WITH_CONDITIONS,
        5.0,
        risks,
        ImplementationState.IMPLEMENTED,
    )


def _auth_requirements(connector_id: str | None, klass: IntegrationAssessmentClass) -> list[str]:
    if connector_id:
        try:
            definition = registry.get_definition(connector_id)
            return [a.value for a in definition.auth_types]
        except Exception:  # noqa: BLE001
            pass
    if klass == IntegrationAssessmentClass.UNIVERSAL_ADAPTER_AVAILABLE:
        return ["api_key", "bearer_token", "basic", "database_credentials"]
    return ["unknown"]


def _permissions(connector_id: str | None) -> list[str]:
    if connector_id:
        try:
            definition = registry.get_definition(connector_id)
            return list(definition.required_scopes)
        except Exception:  # noqa: BLE001
            return []
    return []


def _parse_inventory(content: bytes, filename: str) -> list[dict[str, Any]]:
    lower = filename.lower()
    if lower.endswith(".json"):
        data = json.loads(content.decode("utf-8"))
        if isinstance(data, dict):
            data = data.get("applications", data.get("items", []))
        return [dict(row) for row in data]
    if lower.endswith(".csv") or lower.endswith(".tsv"):
        delimiter = "\t" if lower.endswith(".tsv") else ","
        text = content.decode("utf-8-sig")
        return [dict(row) for row in csv.DictReader(io.StringIO(text), delimiter=delimiter)]
    if lower.endswith((".xlsx", ".xls")):
        try:
            from openpyxl import load_workbook  # optional dependency
        except ImportError as exc:  # pragma: no cover
            raise ValidationError(
                "Excel inventory import requires the 'openpyxl' package."
            ) from exc
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        sheet = workbook.active
        rows = sheet.iter_rows(values_only=True)
        try:
            headers = [str(h) if h is not None else "" for h in next(rows)]
        except StopIteration:
            return []
        return [
            {headers[i]: value for i, value in enumerate(row) if i < len(headers)}
            for row in rows
        ]
    raise ValidationError("Unsupported inventory format; use CSV, TSV, JSON or XLSX.")
