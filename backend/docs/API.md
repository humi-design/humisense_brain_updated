# Layer 1 API Reference

Base path: `/api/v1`. Interactive OpenAPI docs are served at `/docs` when the app runs.

All endpoints except `/health` require an identity. In this build identity is carried by
headers (the deployment is expected to terminate OIDC/JWT at the edge and map it onto these
headers):

| Header | Meaning |
|---|---|
| `X-Tenant-Id` | Tenant scope. **Required**; every query is filtered by it. |
| `X-User-Id` | Acting principal, recorded in the audit log. |
| `X-User-Role` | `admin` \| `operator` \| `viewer`. Writes require `admin`. |

Missing `X-Tenant-Id` → `401`. Insufficient role → `403`. Cross-tenant resource → `404`
(never `403`, to avoid confirming existence).

---

## Health

### `GET /health`
Liveness and readiness. Never requires identity.

```json
{"status":"ok","version":"0.1.0","database":"ok",
 "connectors_registered":69,"connectors_installable":8}
```

### `GET /metrics`
Process counters: requests, syncs, failures.

---

## Connectors (catalogue)

### `GET /connectors`
Query: `category`, `search`, `installable_only`.

Returns `ConnectorDefinition[]`. Each entry carries `implementation_state`, `is_installable`,
auth types, required scopes, supported resources, licence requirements, known limitations and
documentation URL. **`is_installable` is derived from whether a factory is registered, not
from catalogue presence.**

### `GET /connectors/{connector_id}`
One definition. `404` if unknown.

### `GET /connectors/categories`
Distinct category names.

---

## Connections

### `POST /connections`
Requires `admin`.

```json
{
  "connector_id": "github",
  "display_name": "GitHub — Production",
  "configuration": {"base_url": "https://api.github.com", "options": {}},
  "credentials": {"token": "…"},
  "granted_scopes": []
}
```

`201` with the connection. Credentials are encrypted immediately and **never returned**;
the response carries `credential_reference_id` instead. The connection starts `configured` —
never `connected`.

### `GET /connections`
All connections for the tenant.

### `GET /connections/{connection_id}`
One connection. `404` for another tenant's id.

### `POST /connections/{connection_id}/credentials`
Rotates stored credentials. The previous ciphertext is destroyed.

### `POST /connections/{connection_id}/test`
Calls `test_connection()` on the connector. On success the connection becomes `connected`
with health `healthy`, and granted scopes are recorded. On failure it becomes `failed`, the
error is stored and audited, and the failure state is **committed before the error is
returned** so the UI can display it.

### `GET /connections/{connection_id}/resources`
Runs `discover_resources()` against the provider. Returns only resources the granted scopes
authorise.

### `PUT /connections/{connection_id}/resources`
```json
{"external_ids": ["repos", "issues"]}
```
Records the authorised selection. Only selected resources are ever synchronised.

### `POST /connections/{connection_id}/sync-config`
```json
{"mode": "incremental", "page_size": 100, "schedule_cron": null, "enabled": true}
```
Rejects `write_enabled` for read-only connectors.

### `POST /connections/{connection_id}/sync?resource_id=repos&mode=full`
Runs a synchronisation. Returns a `SyncRun`. Failures are committed and re-raised, so a
failed run is always visible and the connection is marked `degraded`.

### `GET /connections/{connection_id}/sync-runs`
Recent runs.

### `POST /connections/{connection_id}/revoke`
Sets `revoked`, destroys credentials, records the actor. Revoked connections cannot sync.

### `DELETE /connections/{connection_id}`
Soft-deletes; credentials destroyed.

---

## Company Technology Discovery

### `POST /discovery/inventory`
`multipart/form-data` with `file` — CSV, TSV, JSON or XLSX containing at least a name column
(`name`, `application`, `application_name`, `app`). Returns created `Assessment[]`.

### `POST /discovery/assessments`
```json
{"application_name":"Acme MES","vendor":"Acme","openapi_available":false,
 "has_api_docs":true,"database_reachable":false,"on_premise_only":true}
```
Returns an `Assessment`. `integration_class` is one of:

`PREBUILT_CONNECTOR_AVAILABLE`, `UNIVERSAL_ADAPTER_AVAILABLE`, `CUSTOM_CONNECTOR_REQUIRED`,
`VENDOR_ASSISTANCE_REQUIRED`, `MANUAL_IMPORT_AVAILABLE`, `INTEGRATION_NOT_FEASIBLE`,
`DISCOVERY_PENDING`.

### `GET /discovery/assessments`, `PATCH /discovery/assessments/{id}`
List and update (e.g. assign to custom connector development).

**Discovery is never authorisation.** An assessment records feasibility only; a separate
explicit connection is always required before any data is read.

---

## Custom connectors

### `GET /custom-connectors/adapter-kinds`
`rest`, `graphql`, `sql`, `file`, `webhook`, `sftp`, `opcua`, `mqtt`, `industrial_gateway`.

### `POST /custom-connectors/validate`
```json
{"name":"check","adapter_kind":"sql","definition":{"dialect":"postgresql",
 "queries":[{"id":"q","sql":"DELETE FROM t"}]}}
```
Returns `{valid, errors, warnings}` without persisting.

### `POST /custom-connectors`
Creates a definition as a `draft`. The validation report is stored with it.

### `POST /custom-connectors/{id}/transition`
```json
{"target": "pending_review"}
```
Stages: `draft → pending_review → approved → published`. Stages cannot be skipped (`422`).
A definition that fails validation cannot be approved. **AI-generated definitions follow the
same path and never activate automatically.**

---

## Synchronisation operations

### `GET /dead-letters`, `POST /dead-letters/{id}/resolve`
Records that could not be processed, and their resolution.

### `GET /audit-logs`
The tenant audit trail, newest first.

### `GET /metrics`
Process counters (unauthenticated, like `/health`).

### `GET /config/public`
Non-secret client configuration: environment, whether the credential key is configured, and
which adapters are enabled. Contains no credential material by construction.

---

## Events (Layer 2 contract)

### `GET /events/contract`
The published contract: schema version, event types, delivery semantics.

### `GET /outbox?limit=100`
Pending events in the transactional outbox.

### `POST /outbox/drain`
Marks pending events as dispatched for a downstream consumer that has pulled them. This is a
manual/administrative hook, not a broker subscription.

---

## Webhooks (inbound)

### `POST /webhooks/{tenant_id}/{connection_id}/{source}`
Raw body plus the provider's signature header. Verified against the connection's stored
webhook secret using the configured scheme (`github`, `sha256`, `slack`). Replayed
deliveries (same delivery id) are acknowledged with `202 {"status":"duplicate"}` and not
reprocessed. Unsigned or invalid deliveries → `401`.

---

## Error shape

```json
{"error": "not_found", "message": "…", "detail": {}}
```

| Code | HTTP |
|---|---|
| `authentication_required` | 401 |
| `authorization_denied` | 403 |
| `not_found` | 404 |
| `validation_error` | 422 |
| `connector_auth_error` | 401 |
| `connector_rate_limited` | 429 |
| `egress_blocked` | 403 |
| `connector_error` | 502 |
| `internal_error` | 500 |


---

## Route index

Verified against the running application:

```
GET     /api/v1/health
GET     /api/v1/metrics
GET     /api/v1/config/public
GET     /api/v1/events/contract
GET     /api/v1/outbox
POST    /api/v1/outbox/drain
GET     /api/v1/audit-logs
GET     /api/v1/dead-letters
POST    /api/v1/dead-letters/{dead_letter_id}/resolve
GET     /api/v1/connectors
GET     /api/v1/connectors/categories
GET     /api/v1/connectors/{connector_id}
GET     /api/v1/connections
POST    /api/v1/connections
GET     /api/v1/connections/{connection_id}
DELETE  /api/v1/connections/{connection_id}
POST    /api/v1/connections/{connection_id}/credentials
POST    /api/v1/connections/{connection_id}/test
GET     /api/v1/connections/{connection_id}/resources
PUT     /api/v1/connections/{connection_id}/resources
POST    /api/v1/connections/{connection_id}/sync-config
POST    /api/v1/connections/{connection_id}/sync
GET     /api/v1/connections/{connection_id}/sync-runs
POST    /api/v1/connections/{connection_id}/revoke
POST    /api/v1/discovery/inventory
GET     /api/v1/discovery/assessments
POST    /api/v1/discovery/assessments
PATCH   /api/v1/discovery/assessments/{assessment_id}
GET     /api/v1/custom-connectors
POST    /api/v1/custom-connectors
PATCH   /api/v1/custom-connectors/{definition_id}
GET     /api/v1/custom-connectors/adapter-kinds
POST    /api/v1/custom-connectors/validate
POST    /api/v1/custom-connectors/{definition_id}/transition
POST    /api/v1/webhooks/{tenant_id}/{connection_id}/{source}
```
