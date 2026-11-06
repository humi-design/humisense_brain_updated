# Humisense Brain — Layer 1: Connector & Sensory Platform

The integration foundation for Humisense: a secure, extensible platform that connects
enterprise applications, authenticates to them, synchronises their data and publishes
well-defined events to the layers above.

Layer 1 owns connectivity. It does not own business task extraction, prioritisation, memory,
reasoning or agent orchestration — those belong to Layer 2 and beyond.

## Status

| Component | State |
|---|---|
| Backend (FastAPI, SQLAlchemy, Alembic) | Complete, 105 tests passing |
| Frontend (React, TypeScript, Vite) | Complete, typechecks and builds |
| Live-verified integrations | **GitHub only** |
| Release recommendation | **CONDITIONAL PASS** — see `backend/docs/FINAL_REPORT.md` |

The honest state of every integration is recorded in `backend/app/connectors/catalogue.py` and
surfaced through the API and the UI. 69 integration targets are catalogued; **8 are actually
connectable**. The rest are labelled `PLANNED` and shown as "Unavailable".

## What Layer 1 provides

- **Connector SDK** — a 12-method lifecycle contract every connector implements.
- **Connector registry** — 69 catalogued targets with authentication types, scopes,
  resources, licence requirements, on-premise needs and known limitations.
- **Prebuilt connectors** — GitHub (`INTEGRATION_VERIFIED`), Slack (`TESTED`), Canary Labs
  historian (`IMPLEMENTED`, not yet verified against real hardware).
- **Universal adapters** — REST, GraphQL, read-only SQL, files (CSV/JSON/XML/XLSX), signed
  webhooks.
- **Custom connector framework** — staged review (draft → pending review → approved →
  published) with validation gates; AI-generated definitions never activate automatically.
- **Secure connection management** — AES-256-GCM credentials bound to tenant and connection,
  rotation, revocation, full audit trail.
- **Synchronisation** — full and incremental, checkpoints, retry with backoff and jitter,
  idempotency, dead letters, manual resync, health monitoring.
- **Company Technology Discovery** — import an application inventory, get a feasibility
  assessment per application across seven integration classes.
- **Layer 2 event contract** — a transactional outbox publishing `connector.record.observed`,
  `connector.sync.completed`, `connector.sync.failed`, `connector.connection.health` and
  `connector.webhook.received`.

## Layout

```
backend/
  app/
    api/routers/      HTTP surface
    connectors/       connector SDK, catalogue, registry, adapters
    core/             config, crypto, egress guard, http client, logging, errors
    db/               SQLAlchemy models and session
    discovery/        company technology discovery
    events/           Layer 2 contract and outbox
    schemas/          typed contracts
    services/         connection management
    sync/             synchronisation engine
  alembic/            migrations (baseline 94473a85bf00)
  tests/              105 tests
  docs/               AUDIT, API, SECURITY, ENVIRONMENT, DEPLOYMENT, FINAL_REPORT
frontend/
  src/pages/          six screens
  src/api/            typed API client
  src/components/     shared UI primitives
```

## Running it

### Backend

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

export HUMISENSE_DATABASE_URL="sqlite+pysqlite:///$(pwd)/humisense_dev.db"
export HUMISENSE_CREDENTIAL_ENCRYPTION_KEY="$(python -c 'import secrets;print(secrets.token_hex(32))')"

alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Or use the helper: `backend/scripts/run_dev.sh`.

### Frontend

```bash
cd frontend
npm install
VITE_TENANT_ID=demo-tenant VITE_USER_ID=admin VITE_USER_ROLE=admin \
  npm run dev -- --host 0.0.0.0 --port 12000
```

Open the app and use the Integration Marketplace to connect GitHub.

### Tests

```bash
cd backend && . .venv/bin/activate && pytest tests/ -q     # 105 passed
cd frontend && npx tsc --noEmit && npm run build
```

## Security

Credentials are encrypted with AES-256-GCM using additional authenticated data that binds
each ciphertext to its tenant and connection, so a copied ciphertext cannot be decrypted.
Every query is tenant-scoped. Outbound requests pass an SSRF guard. Industrial connectors are
read-only by contract. See `backend/docs/SECURITY.md` for the model, and for the residual
risks that are **not** yet closed.

**Identity headers (`X-Tenant-Id`, `X-User-Id`, `X-User-Role`) are trusted by the API.** The
deployment must strip them from inbound client traffic and inject them from the authenticated
session. A deployment that forwards client-supplied identity headers has no tenant isolation.

## Documentation

| Document | Contents |
|---|---|
| `backend/docs/AUDIT.md` | Audit of the pre-existing system and every implemented capability |
| `backend/docs/API.md` | Endpoints, headers, payloads, error codes, route index |
| `backend/docs/SECURITY.md` | Trust boundaries, controls, residual risks, deployment duties |
| `backend/docs/ENVIRONMENT.md` | Every environment variable, including unused ones |
| `backend/docs/DEPLOYMENT.md` | Production deployment and pre-launch checklist |
| `backend/docs/FINAL_REPORT.md` | Final report, verification evidence, release recommendation |

## Licence

Proprietary. © Humisense.
