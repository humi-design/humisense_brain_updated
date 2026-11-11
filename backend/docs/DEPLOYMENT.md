# Deployment Guide — Layer 1

## 1. Topology

Modular monolith. One FastAPI process serving `/api/v1`, one PostgreSQL database, one static
React bundle. No message broker is required: Layer 2 events are written to a transactional
outbox in the same database, so a consumer reads them without a broker.

```
Browser ──HTTPS──> Reverse proxy ──> FastAPI (uvicorn/gunicorn)
                                        │
                                        ├─> PostgreSQL  (state, credentials, outbox)
                                        └─> egress (allow-listed provider APIs)
```

## 2. Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Node.js 20+ (build only)
- A reverse proxy terminating TLS

## 3. Backend

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

export HUMISENSE_ENVIRONMENT=production
export HUMISENSE_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@HOST:5432/humisense'
export HUMISENSE_CREDENTIAL_ENCRYPTION_KEY="$(python -c 'import secrets;print(secrets.token_hex(32))')"
export HUMISENSE_EGRESS_ALLOWED_HOSTS='api.github.com,slack.com'   # private-range exemptions only

alembic upgrade head
gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 4 -b 0.0.0.0:8000
```

On startup the application rewrites the connector registry table from the code catalogue and
logs `connector_registry_synced`. A failure there is logged as a warning and does not stop
the API from serving.

## 4. Frontend

```bash
cd frontend
npm ci
VITE_API_BASE=/api/v1 npm run build      # emits dist/
```

Serve `dist/` from the reverse proxy and proxy `/api` to the backend.

## 5. Reverse proxy sketch

```nginx
server {
    listen 443 ssl;
    server_name integrations.example.com;

    location /api/ { proxy_pass http://127.0.0.1:8000; proxy_set_header Host $host; }
    location /     { root /srv/humisense/frontend/dist; try_files $uri /index.html; }
}
```

## 6. Database migrations

Alembic lives in `backend/alembic/`. The baseline revision is `94473a85bf00`.

```bash
alembic upgrade head          # apply
alembic downgrade -1          # roll back one revision
alembic revision --autogenerate -m "describe change"
```

## 7. Operational checks

| Check | Command | Expected |
|---|---|---|
| Liveness | `curl -s localhost:8000/api/v1/health` | `{"status":"ok",…}` |
| Registry populated | `psql -c "select count(*) from connector_registrations"` | 69 |
| No credential leakage | `grep -ri "token" /var/log/humisense/*.log` | no secret values |
| Outbox draining | `psql -c "select count(*) from event_outbox where published_at is null"` | trending to zero |

## 8. Security checklist before go-live

- [ ] `HUMISENSE_CREDENTIAL_ENCRYPTION_KEY` set from a secret manager, not a file in the repo.
- [ ] `HUMISENSE_EGRESS_ALLOW_PRIVATE=false`.
- [ ] Network-layer egress rules block private ranges (see the DNS-rebinding risk in
      `SECURITY.md` §4 — the application check alone is not sufficient).
- [ ] `HUMISENSE_CORS_ORIGINS` lists only the real frontend origin.
- [ ] TLS verified for every egress call (default; do not disable).
- [ ] Database backups include the credentials table; the encryption key is escrowed
      separately, since a backup without the key cannot decrypt.
- [ ] Log aggregation configured with a redaction rule for `token`, `secret`, `password`,
      `authorization`.
- [ ] Identity headers are injected by the trusted proxy and stripped from inbound client
      requests, so a client cannot spoof `X-Tenant-Id`.
- [ ] Industrial connectors left read-only; confirm no write path is enabled.

## 9. Scaling notes

- The API is stateless; scale horizontally behind the proxy.
- Sync runs execute inline. Long syncs should move to a worker pool; the `SyncRun` model
  already records enough state for a worker to resume from a checkpoint.
- The outbox is append-only and safe for concurrent readers.

## 10. Known operational limitations

- No background scheduler: `schedule_cron` is stored but nothing acts on it yet.
- Webhooks require a publicly reachable callback URL.
- The file adapter only reads inside the per-connection `allowed_roots` list.
- Application-level rate limiting is not implemented; only provider 429 handling exists.
- The SQL adapter applies no statement timeout.
