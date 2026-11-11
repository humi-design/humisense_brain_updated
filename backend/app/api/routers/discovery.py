"""Company Technology Discovery endpoints.

Discovery is authorised-only and is never treated as authorisation to access
data.  Uploading an inventory creates assessments; it does not connect anything.
"""

from __future__ import annotations

from fastapi import APIRouter, File, Query, UploadFile, status

from app.api.deps import AdminPrincipal, CurrentPrincipal, DbSession
from app.api.schemas import AssessmentCreateIn, AssessmentOut, AssessmentUpdateIn
from app.discovery.service import TechnologyDiscoveryService
from app.schemas.contracts import DiscoverySource

router = APIRouter(prefix="/discovery", tags=["discovery"])


@router.get("/assessments", response_model=list[AssessmentOut])
def list_assessments(principal: CurrentPrincipal, db: DbSession) -> list[AssessmentOut]:
    service = TechnologyDiscoveryService(db)
    return [AssessmentOut(**service.to_contract(row).model_dump()) for row in service.list_assessments(principal.tenant_id)]


@router.post("/assessments", response_model=AssessmentOut, status_code=status.HTTP_201_CREATED)
def create_assessment(
    payload: AssessmentCreateIn, principal: AdminPrincipal, db: DbSession
) -> AssessmentOut:
    service = TechnologyDiscoveryService(db)
    row = service.assess_application(
        principal.tenant_id,
        application_name=payload.application_name,
        vendor=payload.vendor,
        category_hint=payload.category_hint,
        source=payload.discovery_source,
        has_api_docs=payload.has_api_docs,
        openapi_available=payload.openapi_available,
        database_reachable=payload.database_reachable,
        on_premise_only=payload.on_premise_only,
        notes=payload.notes,
    )
    return AssessmentOut(**service.to_contract(row).model_dump())


@router.post("/inventory", response_model=list[AssessmentOut], status_code=status.HTTP_201_CREATED)
async def import_inventory(
    principal: AdminPrincipal,
    db: DbSession,
    file: UploadFile = File(...),
    source: DiscoverySource = Query(default=DiscoverySource.CUSTOMER_INVENTORY),
) -> list[AssessmentOut]:
    """Import a customer-provided application inventory (CSV/TSV/JSON/XLSX)."""
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        from app.core.errors import ValidationError

        raise ValidationError("Inventory file exceeds the 10 MB limit.")
    service = TechnologyDiscoveryService(db)
    rows = service.import_inventory(
        principal.tenant_id, content=content, filename=file.filename or "inventory.csv", source=source
    )
    return [AssessmentOut(**service.to_contract(row).model_dump()) for row in rows]


@router.patch("/assessments/{assessment_id}", response_model=AssessmentOut)
def update_assessment(
    assessment_id: str, payload: AssessmentUpdateIn, principal: AdminPrincipal, db: DbSession
) -> AssessmentOut:
    service = TechnologyDiscoveryService(db)
    fields = payload.model_dump(exclude_none=True)
    if "integration_class" in fields:
        fields["integration_class"] = fields["integration_class"].value
    if "status" in fields:
        fields["status"] = fields["status"].value
    row = service.update_assessment(principal.tenant_id, assessment_id, **fields)
    return AssessmentOut(**service.to_contract(row).model_dump())
