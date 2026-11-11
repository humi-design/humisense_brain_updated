"""Webhook ingestion endpoint.

Inbound provider webhooks are verified before anything is processed:
* the connection is resolved within the tenant,
* the signature is verified against the connection's signing secret,
* a delivery id is recorded for replay protection,
* the payload is published as a Layer 2 event.

Unsigned or invalid deliveries are rejected and audited.  Nothing is trusted
merely because it arrived.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Header, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbSession
from app.core.errors import AuthenticationError, NotFoundError
from app.core.logging import get_logger
from app.core.webhook_security import verify_webhook
from app.db import models
from app.schemas.contracts import EventEnvelope

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = get_logger(__name__)

EVENT_WEBHOOK_RECEIVED = "connector.webhook.received"


@router.post("/{tenant_id}/{connection_id}/{source}", status_code=status.HTTP_202_ACCEPTED)
async def receive_webhook(
    tenant_id: str,
    connection_id: str,
    source: str,
    request: Request,
    db: DbSession,
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
    x_signature_256: str | None = Header(default=None, alias="X-Signature-256"),
    x_slack_signature: str | None = Header(default=None, alias="X-Slack-Signature"),
    x_slack_request_timestamp: str | None = Header(default=None, alias="X-Slack-Request-Timestamp"),
    x_github_delivery: str | None = Header(default=None, alias="X-GitHub-Delivery"),
) -> dict:
    connection = db.execute(
        select(models.Connection).where(
            models.Connection.id == connection_id,
            models.Connection.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if connection is None:
        raise NotFoundError("Unknown webhook endpoint.")

    options = (connection.configuration or {}).get("options", {})
    adapter = options.get("adapter", {}) if isinstance(options, dict) else {}
    scheme = str(adapter.get("signature_scheme", "sha256")).lower()

    credential = db.execute(
        select(models.Credential).where(
            models.Credential.connection_id == connection.id,
            models.Credential.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if credential is None:
        raise AuthenticationError("No signing secret is configured for this connection.")

    from app.core.crypto import SealedCredential, get_cipher

    sealed = SealedCredential.from_storage(
        {
            "encrypted_payload": credential.encrypted_payload,
            "nonce": credential.nonce,
            "key_version": credential.key_version,
            "algorithm": credential.algorithm,
        }
    )
    secrets = get_cipher().open(sealed, tenant_id=tenant_id, connection_id=connection.id)
    secret = secrets.get("webhook_secret") or secrets.get("signing_secret") or secrets.get("token")
    if not secret:
        raise AuthenticationError("No signing secret is available for verification.")

    body = await request.body()
    signature = x_hub_signature_256 or x_signature_256 or x_slack_signature
    try:
        verify_webhook(
            scheme=scheme,
            secret=str(secret),
            payload=body,
            signature=signature,
            timestamp=x_slack_request_timestamp,
        )
    except AuthenticationError as exc:
        db.add(
            models.AuditLog(
                tenant_id=tenant_id,
                action="webhook_rejected",
                resource_type="connection",
                resource_id=connection.id,
                detail={"reason": "signature_invalid", "source": source},
            )
        )
        db.commit()
        logger.warning("webhook_rejected", connection_id=connection.id, source=source)
        raise exc

    delivery_id = x_github_delivery or str(uuid.uuid4())
    existing = db.execute(
        select(models.WebhookSignatureRecord.id).where(
            models.WebhookSignatureRecord.connection_id == connection.id,
            models.WebhookSignatureRecord.delivery_id == delivery_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {"status": "duplicate", "delivery_id": delivery_id}

    record = models.WebhookSignatureRecord(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        connection_id=connection.id,
        delivery_id=delivery_id,
    )
    db.add(record)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return {"status": "duplicate", "delivery_id": delivery_id}

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = {"raw": body.decode("utf-8", errors="replace")[:20_000]}

    envelope = EventEnvelope(
        event_id=str(uuid.uuid4()),
        event_type=EVENT_WEBHOOK_RECEIVED,
        tenant_id=tenant_id,
        connection_id=connection.id,
        connector_id=connection.connector_id,
        idempotency_key=f"webhook:{connection.id}:{delivery_id}",
        payload={"source": source, "delivery_id": delivery_id, "body": payload},
    )
    db.add(
        models.EventOutbox(
            id=envelope.event_id,
            tenant_id=tenant_id,
            connection_id=connection.id,
            event_type=envelope.event_type,
            schema_version=envelope.schema_version,
            idempotency_key=envelope.idempotency_key,
            payload=envelope.model_dump(mode="json"),
        )
    )
    db.add(
        models.AuditLog(
            tenant_id=tenant_id,
            action="webhook_received",
            resource_type="connection",
            resource_id=connection.id,
            detail={"source": source, "delivery_id": delivery_id},
        )
    )
    db.commit()
    return {"status": "accepted", "delivery_id": delivery_id, "received_at": datetime.now(timezone.utc).isoformat()}
