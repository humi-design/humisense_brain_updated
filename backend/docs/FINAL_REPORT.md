# Layer 1 — Final Implementation Report

**Project:** Humisense Brain / OS — Layer 1: Connector & Sensory Platform
**Date:** 2026-11-06
**Release recommendation:** **CONDITIONAL PASS**

---

## 1. What was already present

Nothing. The repository held one commit (`92f7f18 Initial commit`), one tracked file
(`README.md`, 25 bytes) and no code of any kind. See `AUDIT.md` §1 for the evidence.

Because there was no pre-existing system, no existing security control, database structure or
API contract was modified or replaced. Every control described here is new.

---

## 2. What was changed

Two defects found during verification were corrected rather than documented as acceptable:

1. **The durable connector registry was never populated.** The API reported 69 registered
   connectors because it read the in-process catalogue, but the `connector_registrations`
   table held 0 rows — any query joining against it would silently return nothing. Startup now
   projects the catalogue into the table (`_sync_connector_registry()` in `app/main.py`) and
   logs the result. Verified: 69 rows, 8 installable.

2. **The catalogue mislabelled working connectors as `planned`.** GitHub and Slack were
   simultaneously shown as "planned" *and* offered a Connect button — exactly the
   contradiction the brief forbids. GitHub is now `INTEGRATION_VERIFIED` (it was exercised
   against the live API), Slack is `TESTED`, and Canary carries an explicit
   "NOT integration-verified" limitation. The UI text and the catalogue state now agree.

Three frontend type errors were also fixed (missing `vite-env.d.ts`, an unused import, a
`ReactNode` narrowing), and the dev server now permits the preview host.

---

## 3. What was newly implemented

**~7,000 lines of backend Python, ~2,600 lines of frontend TypeScript.**

### Backend
- **Connector SDK** — 12 lifecycle methods on an abstract base
  (`validate_configuration`, `test_connection`, `authenticate`, `refresh_credentials`,
  `discover_capabilities`, `discover_resources`, `fetch_records`, `fetch_incremental_records`,
  `subscribe_to_events`, `normalize_metadata`, `health_check`, `disconnect`).
- **Typed contracts** — `ConnectorDefinition`, `ConnectorInstance`, `ConnectionConfiguration`,
  `CredentialReference`, `ConnectorCapability`, `ConnectorResource`, `SyncConfiguration`,
  `SyncCheckpoint`, `SyncRun`, `ConnectorHealth`, `IntegrationAssessment`. Strict Pydantic
  validation; unknown fields rejected.
- **Registry & catalogue** — 69 definitions across communication, email/calendar, meetings,
  documents, CRM, ERP/finance, project management, manufacturing/industrial and HR, each with
  auth types, scopes, resources, licence and on-premise requirements and known limitations.
  Only 8 have working factories; the rest are honestly `PLANNED`.
- **Connectors** — GitHub (`INTEGRATION_VERIFIED`), Slack (`TESTED`), Canary Labs
  (`IMPLEMENTED`, fixture-only).
- **Universal adapters** — REST, GraphQL, SQL (read-only enforced), file (CSV/JSON/XML/XLSX,
  path-confined), webhook receiver (HMAC-verified).
- **Custom connector framework** — draft → pending_review → approved → published, with
  validation gates, no stage skipping, and SQL write statements rejected.
- **Credential vault** — AES-256-GCM with AAD bound to `tenant_id` + `connection_id`.
- **Egress guard** — scheme restriction, private-range denial, explicit block list, and
  address validation before dispatch. Validated addresses are recorded but not yet used to
  pin the connection (see §7).
- **Sync engine** — full and incremental, cursor and time modes, checkpoints, exponential
  backoff with jitter, bounded retries, idempotency, duplicate detection, dead letters,
  manual resync, health monitoring.
- **Layer 2 contract** — `connector.record.observed`, `connector.sync.completed`,
  `connector.sync.failed`, `connector.connection.health`, `connector.webhook.received`;
  transactional outbox, at-least-once, idempotency keys.
- **Discovery** — inventory import and 7-class integration assessment.
- **Audit trail** — every administrative action, plus isolation violations.
- **Alembic baseline** — `94473a85bf00`.

### Frontend (React + TypeScript + Vite, no Streamlit)
Six screens: Integration Marketplace, Connection Wizard, Connected Systems, Company
Technology Discovery, Universal Connector Studio, Integration Health Centre. Status shown is
read from the API; nothing is hard-coded.

---

## 4. What was tested

**105 automated tests, all passing.**

| Suite | Tests | Covers |
|---|---|---|
| `test_adapters.py` | 23 | REST/GraphQL/SQL/file pagination, mapping, read-only rejection, path confinement |
| `test_connectors.py` | 20 | GitHub & Slack contracts, lifecycle, capability discovery |
| `test_api.py` | 16 | Route behaviour, error shapes, role enforcement |
| `test_sync.py` | 12 | Full/incremental, checkpoints, retries, dedup, dead letters |
| `test_egress.py` | 11 | SSRF, private ranges, scheme rejection, allow/block precedence |
| `test_webhooks.py` | 9 | HMAC verification, replay rejection, tenant scoping |
| `test_credentials.py` | 8 | Encryption round-trip, tamper detection, cross-tenant decryption failure |
| `test_tenant_isolation.py` | 6 | Cross-tenant read/write/revoke denial and audit |

Tests use a simulated HTTP transport (`tests/fake_http.py`) for provider calls; SQL and file
adapters execute real code paths. **Mocks are used only for network egress, and that is
labelled here.**

---

## 5. Which integrations were actually verified

**GitHub — `INTEGRATION_VERIFIED`.** Against the live `api.github.com`:

| Step | Observed result |
|---|---|
| Create connection | `7a84a746-1d61-4683-9fba-a4588a2c4833`, status `configured` |
| Test connection | `success: true`, account **`humi-design`**, **304 ms** |
| Discover resources | 31 authorised resources |
| Select resources | `repos`, `issues` |
| Full sync | **28 records**, **6 real pages**, `status: succeeded` |
| Events published | `connector.record.observed`, `connector.sync.completed` |
| Final health | `healthy`, `last_successful_sync` set |
| Audit | `connection_created`, `connection_tested`, `resource_selected`, `sync_started`, `sync_succeeded` |
| Credential exposure | none in any response |

### Additional checks performed live, against the running system

| Check | Method | Observed result |
|---|---|---|
| Tenant isolation | Second tenant `other-tenant` requests the demo connection | `GET` **404**, `GET /connections` returns **0** rows, `POST /sync` **404**, `POST /revoke` **404** |
| Isolation audit | Inspect audit trail after the attempt | `tenant_isolation_violation` recorded with `reason: cross_tenant_access_attempt`, while the caller still saw 404 |
| Failure visibility | Connect GitHub with an invalid token | `test` → `success: false`, "GitHub rejected the supplied token."; connection `status: failed`, `health: unhealthy`, `last_error` populated |
| Failure recovery | Rotate to a valid credential, re-test | `status` back to `configured`; test `success: true` as `humi-design` |
| Encryption at rest | Read the SQLite file directly | Credential stored as 92-char base64 ciphertext; **the raw token does not appear anywhere in the database file** |
| Secret redaction | Audit log and connection payloads | No credential material returned in any response |
| Audit completeness | Inspect action counts | `connection_created`, `connection_tested`, `credential_rotated`, `sync_started`, `sync_succeeded` all present |
| Migration | `alembic upgrade head` on a clean database | 15 domain tables created, revision `94473a85bf00` |
| Full test suite | `pytest tests/ -q` | **105 passed** |
| Frontend | `npx tsc --noEmit`, `npm run build` | Typecheck clean, build succeeded |

**All other connectors: not integration-verified.** Slack and Canary pass only simulated or
fixture tests. Passing a mocked test is not a verified integration and is not reported as one.

---

## 6. Which integrations remain incomplete

| Integration | State | Blocker |
|---|---|---|
| Canary Labs | `IMPLEMENTED`, not verified | No Canary historian, licence or network access available. Read-only guarantee and interface are complete; **must be validated against a real installation before production.** |
| Slack | `TESTED`, not verified | No workspace bot token. |
| 61 catalogued targets | `PLANNED` | No implementation. Shown as "Unavailable" in the UI. |
| OAuth authorization-code redirect | `SCAFFOLDED` | Storage/refresh/rotation work; the interactive redirect handler is not built. |
| Background scheduler | `SCAFFOLDED` | `schedule_cron` is stored; nothing acts on it. Sync is API-triggered. |
| OPC UA / MQTT | `PLANNED` | Catalogued read-only; not implemented. |
| Rate limiting | Not implemented | Config field exists but is unread. |
| DNS-rebinding pinning | Not implemented | Validated IPs are recorded but not used to pin the connection. |

---

## 7. Known security risks

| Risk | Severity | Status |
|---|---|---|
| Identity headers (`X-Tenant-Id`) are trusted from the request | **High if misconfigured** | The deployment **must** strip these from inbound client traffic and inject them from the authenticated session. Documented in `DEPLOYMENT.md` §8. Not enforced in code, because the auth boundary belongs to the edge. |
| **DNS rebinding is not closed.** `guard_url` validates resolved addresses, but the request is sent to the hostname, so `httpx` re-resolves and the validated `resolved_ips` are never pinned. A name that resolves public at validation and private at connect time is not prevented. | **Medium–High** | Private ranges are denied on the validated lookup, and the window is narrow, but the code fix (connect to a pinned validated IP with the original `Host`/SNI) is **not implemented**. Mitigate with network-layer egress rules. Documented in `SECURITY.md` §4. |
| Any public host is reachable; there is no outbound allow-list of public hosts | Medium | `HUMISENSE_EGRESS_ALLOWED_HOSTS` exempts private-range checks, it does not restrict public egress. Enforce an allow-list at the network layer. |
| Per-connection `allow_private` is not audited | Low | The flag exists and is honoured, but no audit record is written when it is set. |
| Development credential key is a fixed all-zero value | Low | Production refuses to start without a real key, so this cannot reach production; local databases must not be promoted. |
| No application-level rate limiting | Low | `HUMISENSE_RATE_LIMIT_DEFAULT_PER_MINUTE` is declared but unread. Only provider 429 handling exists. |
| Blocked egress attempts are not audited | Low | The `egress_blocked` audit action exists in the enum but is never written; a denied request raises an error and is logged, not audited. |
| `connection_updated` / `connection_authenticated` audit actions unused | Low | Declared in the enum, never written. The audit trail is complete for the actions it does record. |
| Sync runs execute inline in the request | Medium | A long sync holds a worker. `SyncRun` checkpoints make a worker pool a drop-in change. |
| No scheduler | Low | Sync is manual or API-driven only. |
| Credential key loss | High | Backups without the escrowed key cannot decrypt stored credentials. Key escrow is a deployment requirement. |
| Canary connector unverified against real hardware | Medium | Explicitly labelled; do not enable in production untested. |
| SQLite used in tests | Low | Production requires PostgreSQL; row-level isolation must be enabled at deployment. |

No credential material was found in API responses or logs during verification.

---

## 8. Performance limitations

- Sync is synchronous and single-process; throughput is bounded by provider rate limits.
- Page sizes are capped at `HUMISENSE_SYNC_MAX_PAGE_SIZE` (default 1000) to bound memory.
- 28 GitHub repositories were fetched in 6 pages without throttling; no large-scale
  throughput benchmark has been performed.
- No caching layer. Every read hits the provider or the database.

---

## 9. Required environment variables

Minimum for production:

```
HUMISENSE_ENVIRONMENT=production
HUMISENSE_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/humisense
HUMISENSE_CREDENTIAL_ENCRYPTION_KEY=<base64 or hex, 32 bytes>
HUMISENSE_EGRESS_ALLOW_PRIVATE=false
```

Full list, with defaults and an explicit note on which settings are unused, in
`docs/ENVIRONMENT.md`.

---

## 10. Database migrations

Baseline revision **`94473a85bf00`** (`layer1_initial_schema`), creating 15 tables:

`tenants`, `users`, `connector_registrations`, `connections`, `credentials`,
`connection_resources`, `sync_configs`, `sync_runs`, `sync_checkpoints`, `event_outbox`,
`dead_letters`, `webhook_deliveries`, `audit_logs`, `integration_assessments`,
`custom_connector_definitions`.

```bash
cd backend && alembic upgrade head
```

---

## 11. API documentation

`docs/API.md` — every endpoint, required headers, request/response shapes and error codes.
Live OpenAPI at `/docs` when running.

---

## 12. Screenshots of the actual UI

Captured from the running application against the live backend, with a real GitHub connection
(`humi-design`, 28 records) present:

| Screen | Shows |
|---|---|
| Integration Marketplace | "69 integration targets catalogued, 8 ready to connect" — planned entries marked "Unavailable", implemented ones marked "Connect" |
| Connection Wizard | 6 steps; name → auth; GitHub token field |
| Connected Systems | **GitHub — Production · github · humi-design · healthy · 304 ms · synced 4s ago** |
| Technology Discovery | Six assessed applications with real classifications (Salesforce/Jira/Workday → prebuilt available; Acme Proprietary MES → vendor assistance; Acme Legacy Billing → manual import) |
| Integration Health Centre | Sync status with the live connection healthy; audit tab showing `sync_succeeded` with `records_written: 28`, `connection_tested` with `latency_ms: 304.46` |
| Universal Connector Studio | Adapter kinds, definition JSON editor, Validate / Save as draft |

---

## 13. Exact commands to run

```bash
# Backend
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export HUMISENSE_DATABASE_URL="sqlite+pysqlite:///$(pwd)/humisense_dev.db"
export HUMISENSE_CREDENTIAL_ENCRYPTION_KEY="$(python -c 'import secrets;print(secrets.token_hex(32))')"
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend (second terminal)
cd frontend
npm install
VITE_TENANT_ID=demo-tenant VITE_USER_ID=admin VITE_USER_ROLE=admin npm run dev -- --host 0.0.0.0 --port 12000

# Tests
cd backend && . .venv/bin/activate && pytest tests/ -q      # 105 passed

# Typecheck & build
cd frontend && npx tsc --noEmit && npm run build
```

A convenience script for the backend is at `backend/scripts/run_dev.sh`.

---

## 14. Acceptance criteria

| # | Criterion | Result |
|---|---|---|
| 1 | A tenant can register an application | **Pass** — connection created over HTTP |
| 2 | A user can authorise a supported connection | **Pass** — GitHub token accepted, stored encrypted |
| 3 | Humisense can test and verify the connection | **Pass** — `humi-design`, 304 ms |
| 4 | The application exposes only authorised resources | **Pass** — 31 discovered, only selected ones synced |
| 5 | Synchronisation retrieves records reliably | **Pass** — 28 records over 6 pages |
| 6 | Events published through a documented Layer 2 contract | **Pass** — `docs/API.md` + `/events/contract` |
| 7 | Failed synchronisation is recoverable | **Pass** — failure persisted, connection `degraded`, dead letters, manual resync |
| 8 | Credentials are protected | **Pass** — AES-256-GCM, tenant-bound, never returned |
| 9 | One tenant cannot access another's connections | **Pass** — 6 isolation tests, 404 + audit |
| 10 | The React UI accurately reflects actual status | **Pass** — screenshots match API state |
| 11 | A customer-specific application can be assessed | **Pass** — Acme Proprietary MES → vendor assistance required |
| 12 | Automated tests and deployment instructions exist | **Pass** — 105 tests, `docs/DEPLOYMENT.md` |

---

## 15. Release recommendation: CONDITIONAL PASS

**Why not an unconditional pass.** The foundation is real, tested and demonstrably working
against a live provider — but the brief's own standard is that "Layer 1 is not complete simply
because the code compiles", and two conditions remain:

1. **Identity is trusted from headers.** Correct tenant isolation depends on the deployment
   stripping `X-Tenant-Id` from inbound traffic. This is a deployment obligation, not a code
   guarantee, and it is the single highest-risk item.
2. **Only one connector is integration-verified.** GitHub is genuinely verified. Slack and
   Canary are not, and Canary in particular is an important industrial target with no live
   installation available to test against.

**Conditions for full pass:**

1. Terminate authentication at the edge and inject identity headers server-side; add a
   regression test that a spoofed header is rejected.
2. Validate the Canary connector against a real historian installation.
3. Set `HUMISENSE_EGRESS_ALLOWLIST` and escrow the encryption key.

**What is genuinely delivered:** a secure, extensible, honest integration foundation with a
working end-to-end connector, a 69-entry catalogue that distinguishes targets from working
integrations, tenant-isolated encrypted credentials, a resilient sync engine, a documented
Layer 2 event contract, and a frontend that reports real state. No functionality is labelled
implemented that is not, and no mock is presented as a live verification.
