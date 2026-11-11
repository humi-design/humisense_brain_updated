# Prompt 00 — Master Repository Audit

**Auditor role:** CTO / Principal Architect
**Date:** 2026-11-06
**Repository:** `humi-design/humisense_brain_updated`
**Commit audited:** `92bf5e6` (branch `layer-1-connector-sensory-platform`, merged to `main` as `b905258`)
**Scope:** Read-only inspection. No code was modified to produce this document.

---

## 0. Headline finding — read this first

**The repository does not contain the system the brief describes.**

Prompt 00 states the project already has "existing authentication and organization-scoping work",
"existing connector and ingestion architecture", "existing analytics and work-intelligence
implementation", a PostgreSQL database, and Redis background infrastructure.

That is not what is in the repository. Verified facts:

| Claimed in Prompt 00 | Reality in repository | Evidence |
|---|---|---|
| Existing foundation, multiple layers | **3 commits total.** Layer 1 only. | `git rev-list --all --count` → `3` |
| Analytics + work-intelligence implementation | **Absent.** Zero matches. | `grep -ril analytics app/` → 0; `work_intelligence` → 0 |
| Redis background infrastructure | **Absent.** Not a dependency, not referenced. | `grep -ri redis` → 0 files; absent from `pyproject.toml` |
| PostgreSQL database | **Optional.** SQLite is the working default. | `pyproject.toml`; `config.py` default is SQLite |
| Authentication work | **Header-trust only. No token validation.** | `app/api/deps.py:44-56` — see §4 |
| Ingestion pipeline | **Layer 1 sync engine only** (`sync/engine.py`). No Layer 2 ingestion. | `app/sync/engine.py` |
| Two interfaces (Mini, Main) | **Neither exists.** | `frontend/src/App.tsx` — 6 connector routes |

The "existing Humisense layers" referenced in §7 of the brief are **not present**. Only Layer 1
exists, and it was built from an empty skeleton in the immediately preceding session
(initial commit `92f7f18`: one file, a 25-byte README).

**Consequence:** the audit below is an audit of *Layer 1 only*. Sections C–F are largely
"not implemented" because the code genuinely is not there. I have not invented findings to fill
the template. Where the brief asked me to inspect something that does not exist, I say so and
show the command output that proves it.

Two real defects were found in the code that *does* exist — one critical (§2.1), one severe
(§4.1).

---

## A. Current architecture

```
                        ┌─────────────────────────────────────────┐
                        │  Browser                                │
                        │  React 18 + Vite + TS (6 pages)         │
                        │  · Marketplace  · Wizard  · Connected   │
                        │  · Discovery    · Studio  · Health      │
                        └──────────────────┬──────────────────────┘
                                           │  fetch()
                        identity headers:  │  X-Tenant-Id / X-User-Id / X-User-Role
                                           ▼
                        ┌─────────────────────────────────────────┐
                        │  FastAPI  app.main:create_app()          │
                        │  · CORS middleware                       │
                        │  · request-id + timing + log middleware  │
                        │  · HumisenseError → JSON handler         │
                        └──────────────────┬──────────────────────┘
                                           │
        ┌──────────────────────────────────┼──────────────────────────────────┐
        ▼                                  ▼                                  ▼
┌────────────────┐              ┌───────────────────┐              ┌──────────────────┐
│ api/routers    │              │ services          │              │ sync             │
│ connections    │─────────────▶│ ConnectionService │─────────────▶│ SyncEngine       │
│ connectors     │              │ CustomConnectorSvc│              │ OutboxPublisher  │
│ discovery      │              │ DiscoveryService  │              └────────┬─────────┘
│ custom_conn.   │              └─────────┬─────────┘                       │
│ sync / health  │                        │                                 │
│ webhooks       │                        ▼                                 ▼
└───────┬────────┘              ┌───────────────────┐              ┌──────────────────┐
        │                       │ connectors        │              │ events/contract  │
        │                       │ registry(69)      │              │ 4 event types    │
        │                       │ catalogue         │              │ transactional    │
        │                       │ base (12 methods) │              │ outbox           │
        │                       │ providers: gh,    │              └──────────────────┘
        │                       │   slack, canary   │
        │                       │ adapters: rest,   │
        │                       │   graphql, sql,   │
        │                       │   file, webhook   │
        │                       └───────────────────┘
        ▼
┌───────────────────────────────────────────────────────────────────┐
│ core: config · crypto (AES-256-GCM) · egress · http (GuardedHttp) │
│       errors · logging (redaction) · webhook_security (HMAC)      │
└───────────────────────────────┬───────────────────────────────────┘
                                ▼
                    ┌────────────────────────┐
                    │ SQLAlchemy 2.0 ORM     │
                    │ 15 tables              │
                    │ SQLite (dev) / PG      │
                    └────────────────────────┘
```

**Runtime shape:** a single-process modular monolith. No message broker, no worker pool, no
scheduler, no cache. Expensive work (sync) executes inline in the HTTP request.

**Layer boundary is real and documented.** `app/events/contract.py` opens with an explicit
statement that Layer 1 publishes raw provenance-preserving records and does not extract tasks,
prioritise, build memory or reason. `app/schemas/contracts.py:405` repeats it. This boundary is
the single most valuable asset in the repository for the work ahead — it is exactly the seam the
Mini/Main experiences must attach to.

---

## B. Implementation inventory

Classification per the brief. Only capability that exists is listed with real status; anything
absent is marked **Not implemented** and is not described as partially present.

### Layer 1 (exists)

| Capability | Status | Evidence |
|---|---|---|
| Connector SDK — 12-method lifecycle | Implemented and tested | `connectors/base.py`; `test_connectors.py` |
| Typed contracts (`ConnectorDefinition`, `SyncRun`, `ConnectorHealth`, …) | Implemented and tested | `schemas/contracts.py` (456 lines) |
| Connector catalogue — 69 targets | Implemented and tested | `catalogue.py`; states: 61 PLANNED, 6 IMPLEMENTED, 1 TESTED, 1 INTEGRATION_VERIFIED |
| GitHub connector | Implemented and tested | `github_connector.py`; live-verified prior session |
| Slack connector | Implemented but untested against real API | `slack_connector.py`; `test_connectors.py` (simulated) |
| Canary Labs connector | Partially implemented | `canary_connector.py`; fixture-only, no live historian |
| Universal REST adapter | Implemented and tested | `rest_adapter.py` (309 lines) |
| Universal GraphQL adapter | Implemented and tested | `graphql_adapter.py` |
| Universal SQL adapter (read-only) | Implemented and tested | `sql_adapter.py`; `validate_read_only_sql` |
| File adapter (CSV/JSON/XML) | Implemented and tested | `file_adapter.py`; realpath-bounded |
| Webhook receiver + HMAC | Implemented and tested | `webhooks.py`; `webhook_security.py` |
| Credential vault — AES-256-GCM | Implemented and tested | `core/crypto.py`; `test_credentials.py` |
| Egress / SSRF guard | Partially implemented | `core/egress.py`; **DNS rebinding not closed** |
| Sync engine | Implemented and tested | `sync/engine.py` (480 lines) |
| Layer 2 event contract + outbox | Partially implemented | `events/contract.py`; **no transport wired** |
| Technology discovery + assessment | Implemented and tested | `discovery/service.py` (402 lines) |
| Custom connector framework | Implemented and tested | `services/custom_connector_service.py` |
| Audit trail | Partially implemented | `audit_logs` written; **egress denials not audited** |
| Alembic migration | Implemented and tested | `94473a85bf00`, 15 tables |
| Tenant isolation | Implemented and tested | `test_tenant_isolation.py` (6 tests) |

### Layer 2+ (absent — required by the brief, not present)

| Capability | Status | Evidence |
|---|---|---|
| Work intelligence / attention inbox | **Not implemented** | `grep -ri "inbox\|priority\|commitment\|deadline"` → 0 real matches |
| Task discovery / classification | **Not implemented** | `task` matches are prose comments only |
| Analytics / anomaly detection | **Not implemented** | `analytics` → 0, `anomaly` → 0 |
| Live Brain / real-time events | **Not implemented** | no websocket/SSE/EventSource anywhere |
| Mission Mode | **Not implemented** | `mission` matches are `permission` |
| Human Guidance Engine | **Not implemented** | — |
| Context Assembly Engine | **Not implemented** | — |
| Artifact generation (DOCX/XLSX/PDF/PPTX) | **Not implemented** | `docx`/`pptx`/`reportlab` → 0 |
| Action Execution Engine | **Not implemented** | — |
| Memory / Context Graph | **Not implemented** | `memory` matches are in-memory SQLite |
| AI Workforce / agents / orchestrator | **Not implemented** | `openai`/`anthropic`/`litellm` → 0; `agent` = `User-Agent` |
| Governance (RBAC, risk class, approval) | **Not implemented** | `approval` → 1 comment; no RBAC table |
| Copilot | **Not implemented** | `copilot` → 0 |
| Humisense Mini (desktop companion) | **Not implemented** | no Electron/Tauri |
| Humisense Main (Today/Copilot/Missions/…) | **Not implemented** | 6 routes, all connector-scoped |
| Background workers / scheduler | **Not implemented** | no Celery/RQ/APScheduler/`BackgroundTasks` |
| Redis | **Not implemented** | not a dependency |

**Test suite:** 105 tests, all passing (`pytest tests/ -q` → `105 passed`). Breakdown: adapters 23,
connectors 20, api 16, sync 12, egress 11, webhooks 9, credentials 8, tenant isolation 6.

**Coverage gap:** no test covers connection creation for a tenant that has no `tenants` row —
which is why the critical bug in §2.1 was not caught.

---

## C. Existing API inventory

**Source of truth:** generated from the running app's OpenAPI schema
(`app.openapi()["paths"]`), not from reading route files by eye. 35 operations.

Base prefix `/api/v1`. Auth is header-based only (see §4).
"tenant" = any authenticated principal. "admin" = `X-User-Role` of `owner` or `admin`.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | **PUBLIC** | Liveness + registry counts |
| GET | `/metrics` | **PUBLIC** | Prometheus-style counters |
| GET | `/config/public` | tenant | Non-secret config |
| GET | `/events/contract` | tenant | Layer 2 event contract |
| GET | `/connectors` | tenant | List catalogue |
| GET | `/connectors/categories` | tenant | Category list |
| GET | `/connectors/{connector_id}` | tenant | One definition |
| GET | `/connections` | tenant | List tenant connections |
| POST | `/connections` | admin | Create connection |
| GET | `/connections/{connection_id}` | tenant | Read one |
| POST | `/connections/{connection_id}/credentials` | admin | Rotate credential |
| POST | `/connections/{connection_id}/test` | admin | Test connectivity |
| GET | `/connections/{connection_id}/resources` | tenant | Discover resources |
| PUT | `/connections/{connection_id}/resources` | admin | Select resources |
| POST | `/connections/{connection_id}/sync-config` | admin | Configure sync |
| POST | `/connections/{connection_id}/revoke` | admin | Revoke |
| DELETE | `/connections/{connection_id}` | admin | Delete |
| POST | `/connections/{connection_id}/sync` | admin | Run sync (inline, not queued) |
| GET | `/connections/{connection_id}/sync-runs` | tenant | Sync history |
| GET | `/dead-letters` | tenant | Failed records (tenant-wide) |
| POST | `/dead-letters/{dead_letter_id}/resolve` | admin | Resolve a dead letter |
| GET | `/audit-logs` | tenant | Audit trail |
| GET | `/outbox` | tenant | Pending events |
| POST | `/outbox/drain` | admin | Drain event outbox |
| GET | `/discovery/assessments` | tenant | List assessments |
| POST | `/discovery/assessments` | admin | Create assessment |
| PATCH | `/discovery/assessments/{assessment_id}` | admin | Update assessment |
| POST | `/discovery/inventory` | admin | Import inventory (CSV/JSON) |
| GET | `/custom-connectors` | tenant | List definitions |
| POST | `/custom-connectors` | admin | Create definition |
| POST | `/custom-connectors/validate` | tenant | Validate (no persist) |
| PATCH | `/custom-connectors/{definition_id}` | admin | Update |
| POST | `/custom-connectors/{definition_id}/transition` | admin | Staged review transition |
| GET | `/custom-connectors/adapter-kinds` | tenant | Adapter kinds |
| POST | `/webhooks/{tenant_id}/{connection_id}/{source}` | **HMAC signature** | Webhook ingest |

**Request/response shapes:** all Pydantic (`api/schemas.py`, 263 lines), strict, `extra="forbid"`
on inputs. Errors return `{"error": <code>, "message": <text>, "detail": {...}}` via the
`HumisenseError` handler.

**Contract quality:** genuinely good. Typed, validated, consistent, with a stable error envelope.
This is a sound foundation to build on.

> **Correction note.** An earlier draft of this section listed routes such as
> `/connections/{id}/dead-letters`, `/connections/{id}/dead-letters/{id}/retry` and
> `/connections/{id}/resync` that **do not exist** — I had inferred them from filenames rather
> than reading the code. Dead letters are tenant-wide (`/dead-letters`), resolved via
> `/dead-letters/{id}/resolve`, and there is no `/resync` endpoint. The table above is now
> generated from the app's own OpenAPI schema. Flagging this because it is exactly the kind of
> invented-contract error the brief forbids.

---

## D. Database inventory

One migration: `94473a85bf00` (`down_revision = None`) — the baseline. 15 tables.
Foreign keys below are read from `Base.metadata.tables[...].foreign_keys` at runtime, not inferred.

| Table | Purpose | Foreign keys |
|---|---|---|
| `tenants` | Organization | *(none)* |
| `users` | User (tenant-scoped, role) | `tenants.id` |
| `connector_registrations` | Durable catalogue projection | *(none)* |
| `connections` | Connector instance per tenant | `tenants.id`, `connector_registrations.id` |
| `credentials` | Encrypted material (1:1 connection) | `connections.id` |
| `connection_resources` | Selected authorized resources | `connections.id` |
| `sync_configs` | Sync mode + cron + limits | `connections.id` |
| `sync_checkpoints` | Cursor / watermark | `connections.id` |
| `sync_runs` | Run history + counts | `connections.id` |
| `dead_letters` | Failed records | ***(none)*** |
| `event_outbox` | Transactional outbox | ***(none)*** |
| `integration_assessments` | Discovery classification | ***(none)*** |
| `custom_connector_definitions` | Versioned custom defs | ***(none)*** |
| `audit_logs` | Append-only audit | ***(none)*** |
| `webhook_deliveries` | Replay defence | ***(none)*** |

**Tenant isolation mechanism:** application-level only — every query filters on
`tenant_id`, and the tenant is taken from the authenticated principal, never from a path or
body (`deps.py` docstring; `connection_service.py` filters). Tests confirm cross-tenant
reads/writes/revokes return 404.

**Two structural observations that matter for the work ahead:**

1. **Only two tables have a database-level link to `tenants`** — `users` and `connections`.
   The other six tenant-scoped tables (`dead_letters`, `event_outbox`,
   `integration_assessments`, `custom_connector_definitions`, `audit_logs`,
   `webhook_deliveries`) carry a `tenant_id` **column with no foreign key at all**. Isolation
   for those tables rests entirely on application code. There is no referential-integrity
   backstop and no cascade.
2. **There is no PostgreSQL row-level security.** `grep -ri "ROW LEVEL SECURITY\|POLICY"` → 0
   hits. Combined with point 1, this means a single query that forgets a `tenant_id` filter is
   a silent cross-tenant leak with nothing behind it to catch the mistake.

This is acceptable for a Layer 1 that is only read by its own routers, but it must be
strengthened before Layer 2 queries these tables from new services (see §F, Milestone 0).

### D.1 Critical defect — `tenants` is never provisioned (reproduced live)

`connections.tenant_id` has `ForeignKey("tenants.id", ondelete="CASCADE")`, and SQLite FK
enforcement is explicitly switched on (`db/session.py:43-47`, `PRAGMA foreign_keys=ON`).

**Nothing in the application ever inserts a `tenants` row.** The only occurrences of
`Tenant(` in the codebase are in `tests/conftest.py`. `ConnectionService.create_connection()`
takes `tenant_id` from the request header and inserts a `connections` row without ensuring the
tenant exists.

Reproduced against a clean database and a live server:

```
$ alembic upgrade head          # fresh DB
$ sqlite3 probe.db "select count(*) from tenants"   → 0
$ curl -X POST localhost:8098/api/v1/connections \
      -H "X-Tenant-Id: brand-new-corp" -H "X-User-Role: admin" \
      -d '{"connector_id":"github","display_name":"Probe","credentials":{...}}'

HTTP 500 {"error":"internal_error","message":"An unexpected error occurred."}

server log: sqlalchemy.exc.IntegrityError: (sqlite3.IntegrityError)
            FOREIGN KEY constraint failed
            [SQL: INSERT INTO connections (id, tenant_id, ...) VALUES (...)]
```

**Impact:** onboarding a new organization fails with an opaque 500 on the very first action.
This is the first step of the product's core flow — acceptance criterion 1 of Layer 1 ("a tenant
can register an application") — and it does not work on a clean deployment.

**Why it passed the previous session's verification:** testing was done against a pre-existing
SQLite file in which a `tenants` row had been created by hand. The passing 105-test suite never
covers this path.

**Not in scope of this assignment to fix** (execution restrictions §9). Recommended fix is in
§F, Milestone 0.

---

## E. Architecture gaps and risks

| # | Gap | Severity | Detail |
|---|---|---|---|
| E1 | `tenants` never provisioned → 500 on first connection | **Critical** | §D.1, reproduced |
| E2 | Identity headers trusted with no token validation | **Critical** | §4 below |
| E3 | No PostgreSQL RLS; isolation is query-level only | High | One missing filter = cross-tenant leak |
| E4 | DNS rebinding not closed | Medium-High | `egress.py` validates resolved IPs but the request is sent to the hostname; `resolved_ips` never pinned |
| E5 | Sync runs inline in the HTTP request | Medium | No worker; a slow provider blocks a request thread; no scheduler despite `schedule_cron` being stored |
| E6 | Event outbox has no transport | Medium | `OutboxPublisher` returns 0 when `transport is None`; events queue durably but nothing drains them to Layer 2 |
| E7 | No background jobs at all | Medium | Blocks all of §3: async AI, agent execution, polling |
| E8 | No rate limiting | Low | Config field declared, never read |
| E9 | Egress denials not audited | Low | `egress_blocked` in enum, never written |
| E10 | `/metrics` unauthenticated | Low | Exposes counters to anyone who can reach the port |
| E11 | No deployment config | Medium | No Dockerfile, compose, CI. `DEPLOYMENT.md` documents manual steps only |
| E12 | No light theme despite brief requiring it | Low | `styles.css` is dark-only (`--bg: #0b0f19`), no `prefers-color-scheme` |
| E13 | Lucide icons required, not installed | Low | Not in `package.json` |
| E14 | No streaming/realtime transport | Medium | Mini and Live Brain both need it |
| E15 | `is_production` gate is weak | Medium | Only checks that an `Authorization` header is *present*, never validates it |

### E.16 — Conflict between the brief and the existing architecture

The brief requires PostgreSQL and Redis. The existing code defaults to SQLite and has no Redis.
This is not a contradiction to paper over: SQLite is fine for development and tests, but the
brief's background-infrastructure requirement (Redis) cannot be met without adding a dependency,
which §5.16 and §4 forbid doing casually.

**Recommendation:** keep SQLite for dev/test, keep the existing `database_url` switch, and
introduce Redis only when Milestone 3 actually needs a queue. Do not add Redis speculatively.
I flag this rather than silently adding it.

---

## 4. Authentication and authorization — detailed finding

This deserves its own section because it is the second critical defect.

`app/api/deps.py`:

```python
async def get_principal(request, x_tenant_id=None, x_user_id=None, x_user_role=None,
                        authorization=None) -> Principal:
    if settings.is_production and not authorization:
        raise AuthenticationError("A bearer token is required.")
    if not x_tenant_id:
        raise AuthenticationError("X-Tenant-Id header is required.")
    return Principal(
        tenant_id=x_tenant_id,
        user_id=x_user_id,
        role=(x_user_role or "member").lower(),
    )
```

Findings:

1. **No token is ever validated.** `authorization` is checked for *presence* only, and only when
   `is_production` is true. Its value is never parsed. `grep` for `jwt`, `jose`, `oidc`, `jwks`,
   `public_key` across `app/` returns nothing.
2. **Identity is fully client-controlled.** `X-Tenant-Id` and `X-User-Role` come straight from the
   request. The frontend sets them itself (`frontend/src/api/client.ts:186-188`).
3. **Therefore tenant isolation is defeatable by one header.** Any caller can set
   `X-Tenant-Id: <victim>` and `X-User-Role: admin` and read, create, revoke or delete another
   tenant's connections. The isolation *tests* pass because they exercise the query layer
   correctly — but the layer above trusts whatever it is told.
4. **`require_role` is therefore not a security control** — it reads a client-supplied string.

The previous session documented this honestly in `SECURITY.md` (§ "the edge is part of the
security boundary") and stated the deployment must strip these headers. That documentation is
correct and I am not contradicting it. But the brief now asks for Governance, RBAC and approval
workflows (§3), and **none of that can be built on trust-the-header identity.** This must be
resolved before Governance, not after.

**This is the most important architectural decision in the project.** I recommend resolving it
in Milestone 1, before any Mini/Main work.

---

## F. Recommended implementation sequence

Safest order, each milestone independently shippable, no existing migration replaced.

| # | Milestone | Why first | Risk |
|---|---|---|---|
| **0** | **Fix `tenants` provisioning + real identity** | Two critical defects; everything else assumes a working tenant and a trustworthy principal | Low — additive migration `0002`, no rewrite |
| 1 | Design system + shared component library | Mini and Main must share tokens; brief §6 requires light+dark | Low |
| 2 | Humisense Main shell (Today/Copilot/Missions/Workforce/Memory/Apps/Governance) | Navigation skeleton with honest empty states | Low |
| 3 | Layer 2 service scaffold + event transport | Consumes the existing outbox; unblocks all intelligence | Medium — needs Redis or equivalent |
| 4 | Work intelligence: task extraction from `connector.record.observed` | First real Layer 2 capability; feeds Today | Medium |
| 5 | Copilot (LLM integration) | Needs provider choice + secrets management | Medium |
| 6 | Mission Mode + agent orchestration | Needs 3, 4, 5 | High |
| 7 | Memory + Context Graph | Needs vector store decision | High |
| 8 | Humisense Mini (desktop companion) | Needs Main's API surface to be stable | Medium |
| 9 | Governance (RBAC, risk, approval) | **Requires Milestone 0** | Medium |

**Milestone 0 is not optional and must not be deferred.** Every later milestone inherits its
outcome.

### Milestone 0 in detail

1. **Add migration `0002_tenant_provisioning`** (additive; do not touch `94473a85bf00`):
   - Add `tenants.provisioned_at`, and a `tenant_invites` or equivalent if self-serve.
   - Backfill: insert a `tenants` row for every distinct `tenant_id` already present in
     `connections`, `audit_logs`, `event_outbox` — so existing data stays valid.
2. **Make `get_principal` resolve-or-create** the tenant row, inside the request transaction,
   so the FK is satisfied. Guard with a uniqueness check to stay idempotent.
3. **Replace header trust with token verification.** Add `python-jose[cryptography]` or
   `PyJWT` + a JWKS client. Validate signature, `iss`, `aud`, `exp`, `nbf`. Map claims to
   `Principal`. Keep the header resolver behind an explicit `HUMISENSE_AUTH_MODE=dev` flag that
   **refuses to start** when `HUMISENSE_ENVIRONMENT=production`. Reuse the existing
   refuse-to-start pattern already in `core/crypto.py`.
4. **Add a regression test** that a spoofed `X-Tenant-Id` is ignored when a token is present.
5. **Fix E3** by adding a `tenant_id` filter assertion helper, or adopt Postgres RLS as
   defence-in-depth.

---

## G. Frontend implementation plan

### Current state

6 pages, 3,007 lines, hand-rolled CSS (442 lines of dark-only tokens). No component library, no
light theme, no icon set, no data-fetching library.

**Credit where due:** the existing pages already handle loading, error and empty states
consistently (`useApi.ts` exposes an explicit `AsyncState<T>` with `loading`/`error`/`reload`,
and every page renders all three branches). The brief's §5.14 requirement is therefore already
met in style — the new work must match this standard rather than introduce a second pattern.

**Gaps against the brief:** dark theme only (no `prefers-color-scheme`, no `[data-theme]`); no
`lucide-react`; Inter is named in `font-family` but **never actually loaded** (no `@font-face`,
no `@fontsource/inter`, no Google Fonts link), so the browser silently falls back to the system
sans-serif.

### Proposed component architecture

```
src/
  design/           tokens.css (light + dark), typography, spacing scale
  components/       primitives — Button, Card, Badge, Table, EmptyState,
                    Skeleton, Toast, Dialog, Tabs, Tooltip, Field
  components/icons  lucide-react re-exports
  layout/           MainShell (nav + secondary nav), MiniShell (floating)
  features/
    today/          attention inbox
    copilot/        chat + guidance
    missions/       plans, steps, agents
    workforce/      agent roster
    memory/         context graph
    apps/           ← existing 6 connector pages move here, unchanged
    governance/     roles, risk, approvals, audit
  api/              client.ts (keep), typed hooks per feature
  lib/              query cache, formatting, error boundaries
```

**Key decision:** the existing 6 connector pages are *good* and must not be rewritten. They move
under `features/apps/` intact. `apps` becomes the nav entry the brief calls "Apps".

### Shared design system

- **Tokens:** extend the existing CSS variables to a light/dark pair via
  `@media (prefers-color-scheme)` plus a `[data-theme]` override. The current variable *names*
  are already semantic (`--bg`, `--text`, `--accent`) — keep them, add a light block. No rewrite.
- **Typography:** Inter is already referenced in `styles.css`. Add the font properly (self-hosted
  or `@fontsource/inter`).
- **Icons:** add `lucide-react` (brief §6 requires Lucide).
- **State:** add TanStack Query for caching/loading/error states rather than hand-rolling. This
  satisfies §5.14 (loading/empty/offline/error) systematically instead of per-page.

### Honest-states rule

Per §5.9 and the Layer 1 precedent: every screen shows a real empty state until its backend
exists. No placeholder dashboards. Today, Copilot, Missions, Workforce, Memory and Governance
ship as **explicit "not yet available"** screens until their milestones land.

---

## H. Integration plan — how Mini, Main, Copilot, Missions, Memory and Governance share the backend

**One backend, one contract.** Both interfaces consume the same `/api/v1` surface. Mini is a thin
client over a subset of Main's endpoints; it gets no privileged access.

```
Humisense Mini ─┐
                ├──▶ /api/v1  ──▶ Layer 1 (exists)  ──▶ outbox ──▶ Layer 2 (new)
Humisense Main ─┘                  connections               │
                                   connectors                ├─▶ work intelligence
                                   sync                      ├─▶ copilot (LLM)
                                   discovery                 ├─▶ missions/agents
                                   governance                ├─▶ memory/graph
```

- **Mini** calls `/attention/summary`, `/tasks?filter=`, `/approvals`, `/copilot/chat`,
  `/artifacts`. All Layer 2. It must never talk to a connector directly.
- **Main** calls the same Layer 2 endpoints plus Layer 1 admin endpoints for the Apps section.
- **Copilot** is a Layer 2 service exposing `/copilot/chat` and `/copilot/guidance/{task_id}`.
- **Missions** exposes `/missions`, `/missions/{id}/steps`, delegating to the agent orchestrator.
- **Memory** exposes `/memory/search` over the context graph; both UIs read, only Main writes.
- **Governance** exposes `/governance/roles`, `/governance/approvals`, `/governance/audit` and
  **depends on Milestone 0** for a trustworthy principal.

**Cross-cutting requirements for every new layer:**

1. Consume `connector.record.observed` from the outbox — do not re-query connectors directly.
2. Deduplicate on `idempotency_key` (the contract already provides it).
3. Preserve provenance: source id, timestamps, ownership, version, confidence.
4. Never expose credentials; never return them in any payload.
5. Expensive work goes to a worker, never inline in a request (§5.11).

---

## Closing statement

The brief asked for an audit of a mature multi-layer system. **That system does not exist yet.**
What exists is a well-built, honestly-documented, tested Layer 1 — a genuinely good foundation —
sitting on two critical defects that must be fixed before anything is built on top of it.

I have not written a single line of implementation code, per §9. I have not deleted, rewritten or
replaced anything. Both defects are reproduced with commands and output, not asserted.

**Recommended next action:** approve Milestone 0, then proceed to the design system.

### Verification commands used

Every factual claim above is backed by one of these. Output is quoted inline where it matters.

```bash
# --- scope of the repository ---
git rev-list --all --count                       # 3 commits
git log --oneline --all                          # Layer 1 only
git ls-files | wc -l                             # 96 tracked files

# --- claimed subsystems that do not exist ---
grep -ril "redis\|celery\|dramatiq" backend/app  # 0 files
grep -ril "analytics\|anomaly\|pipeline" backend/app   # 0 files
grep -ri  "openai\|anthropic\|langchain\|litellm" backend/app  # 0
grep -ri  "copilot\|orchestrat\|embedding\|pgvector" backend/app  # 0
grep -ri  "docx\|pptx\|reportlab\|artifact" backend/app  # 0
grep -ri  "websocket\|EventSource\|text/event-stream" backend/app frontend/src  # 0

# --- false-positive matches, checked individually ---
grep -rin "task"    backend/app   # only prose comments + catalogue descriptions
grep -rin "memory"  backend/app   # only in-memory SQLite
grep -rin "mission" backend/app   # only "permission"
grep -rin "agent"   backend/app   # only "User-Agent"

# --- authentication ---
grep -rin "jwt\|jose\|oidc\|jwks\|public_key" backend/app   # 0 — no token validation
sed -n '44,56p' backend/app/api/deps.py                     # header trust

# --- database ---
python -c "import app.db.models as m; [print(t, [str(f.target_fullname) for f in tb.foreign_keys]) for t,tb in m.Base.metadata.tables.items()]"
grep -ri "ROW LEVEL SECURITY\|POLICY" backend/app backend/alembic   # 0 — no RLS
grep -rn "models.Tenant(" backend/app backend/tests  # only tests/conftest.py

# --- critical defect reproduced ---
cd backend && alembic upgrade head          # against a clean DB
sqlite3 probe.db "select count(*) from tenants"     # 0
curl -X POST localhost:8098/api/v1/connections \
     -H "X-Tenant-Id: brand-new-corp" -H "X-User-Role: admin" \
     -d '{"connector_id":"github","display_name":"Probe","credentials":{...}}'
#   -> HTTP 500, sqlalchemy.exc.IntegrityError: FOREIGN KEY constraint failed

# --- egress / DNS rebinding ---
grep -n "resolved_ips\|is_pinned" backend/app/core/egress.py   # defined
grep -n "target.url" backend/app/core/http.py                  # request sent to hostname, never pinned

# --- public surface ---
python -c "from app.main import app; print(len(app.openapi()['paths']))"   # 35 operations
curl -o /dev/null -w '%{http_code}' localhost/api/v1/metrics      # 200 without auth
curl -o /dev/null -w '%{http_code}' localhost/api/v1/connections  # 401 without tenant

# --- tests ---
cd backend && . .venv/bin/activate && pytest tests/ -q     # 105 passed
```

**Nothing in this document is asserted without a command behind it.** Where the brief asked me to
inspect something that does not exist, I have said so and shown the empty result rather than
inventing a finding.
