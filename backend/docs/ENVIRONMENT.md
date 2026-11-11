# Environment Variables

Every backend variable is declared in `app/core/config.py` and read by pydantic-settings with
the prefix `HUMISENSE_`. This document lists only variables that exist in the code. A `.env`
file in the working directory is also read.

Frontend variables use the `VITE_` prefix and are read by Vite at build time.

## Backend — required in production

| Variable | Default | Purpose |
|---|---|---|
| `HUMISENSE_CREDENTIAL_ENCRYPTION_KEY` | *(none)* | Master key for connector credentials. 32 bytes, base64 or hex encoded. **Startup fails in production if unset.** |
| `HUMISENSE_DATABASE_URL` | `sqlite+pysqlite:///./humisense.db` | SQLAlchemy URL. Use PostgreSQL in production. |

### Development fallback for the master key

When `HUMISENSE_CREDENTIAL_ENCRYPTION_KEY` is unset and the environment is **not** production,
the cipher falls back to a fixed all-zero 32-byte key. This exists so local runs work without
setup. It is **not** secure and **not** derived from anything secret — credentials created in
development are effectively unencrypted. Production refuses to start without a real key.

Generate a key with:

```bash
python -c "from app.core.crypto import generate_master_key; print(generate_master_key())"
```

## Backend — runtime

| Variable | Default | Purpose |
|---|---|---|
| `HUMISENSE_ENVIRONMENT` | `development` | Any value matching `production`/`prod` enables production rules. |
| `HUMISENSE_DEBUG` | `false` | Verbose, non-JSON logging. |
| `HUMISENSE_API_PREFIX` | `/api/v1` | API mount point. |
| `HUMISENSE_CREDENTIAL_KEY_VERSION` | `1` | Key version recorded with each ciphertext, to support key rotation. |

## Backend — egress and SSRF

| Variable | Default | Purpose |
|---|---|---|
| `HUMISENSE_EGRESS_ALLOW_PRIVATE` | `false` | Globally permit private-range targets. Keep `false` in production. |
| `HUMISENSE_EGRESS_ALLOWED_HOSTS` | `[]` | Comma-separated or JSON list. A listed host bypasses the private-range check (but never the explicit block list). |
| `HUMISENSE_EGRESS_BLOCKED_HOSTS` | `[]` | Comma-separated or JSON list. Always blocked; takes precedence over the allow list. |
| `HUMISENSE_EGRESS_CONNECT_TIMEOUT_SECONDS` | `10.0` | Connect timeout for guarded requests. |

**Important:** `HUMISENSE_EGRESS_ALLOWED_HOSTS` is *not* a general outbound allow-list. It is
an exemption from the private-address check. With the default empty value, any **public** host
is reachable and private addresses are denied. There is currently no way to restrict egress to
a fixed set of public hosts; do that at the network layer.

## Backend — connector runtime

| Variable | Default | Purpose |
|---|---|---|
| `HUMISENSE_CONNECTOR_REQUEST_TIMEOUT_SECONDS` | `30.0` | Per-request timeout. |
| `HUMISENSE_CONNECTOR_MAX_RETRIES` | `5` | Retries per request before failing. |
| `HUMISENSE_CONNECTOR_MAX_PAGES` | `10000` | Hard cap on pages per sync, to bound runaway pagination. |
| `HUMISENSE_CONNECTOR_PAGE_SIZE` | `100` | Default page size requested from providers. |

## Backend — synchronisation

| Variable | Default | Purpose |
|---|---|---|
| `HUMISENSE_SYNC_BATCH_SIZE` | `500` | Records processed per batch. |
| `HUMISENSE_SYNC_MAX_RETRIES` | `5` | Retries per batch. |
| `HUMISENSE_SYNC_BACKOFF_BASE_SECONDS` | `1.0` | Exponential backoff base; jitter is added. |
| `HUMISENSE_SYNC_BACKOFF_MAX_SECONDS` | `120.0` | Backoff ceiling. |

## Backend — authentication and authorization

Identity comes from one of two mutually exclusive sources, selected by
`HUMISENSE_AUTH_MODE`. `Settings` validates the configuration at startup and refuses to
start if it is unusable or unsafe. See `docs/MILESTONE_0.md` for the full model.

### Choosing a mode

| Mode | When to use | Identity source |
|---|---|---|
| `oidc` | **Any real deployment.** | A verified bearer JWT. Role and tenant come from the `users` row the verified subject maps to. |
| `header` | Local development and tests only. | `X-Tenant-Id` / `X-User-Id` / `X-User-Role`, trusted as sent. |

`header` mode **refuses to start** unless `HUMISENSE_ENVIRONMENT` is one of `development`,
`dev`, `local`, `test`, `testing`. It cannot be enabled in production.

### OIDC settings

| Variable | Default | Purpose |
|---|---|---|
| `HUMISENSE_AUTH_MODE` | `header` | `oidc` or `header`. |
| `HUMISENSE_AUTH_OIDC_ISSUER` | — | **Required for `oidc`.** Exact `iss` value. Must match the provider's token exactly, including any trailing slash. |
| `HUMISENSE_AUTH_OIDC_AUDIENCE` | — | **Required for `oidc`.** Expected `aud` — the API audience or client id. |
| `HUMISENSE_AUTH_OIDC_JWKS_URL` | — | **Required for `oidc`** unless `HUMISENSE_AUTH_OIDC_HMAC_SECRET` is set. Public key set for signature verification. |
| `HUMISENSE_AUTH_OIDC_ALGORITHMS` | `RS256,ES256` | Comma-separated or JSON allow-list. `none` is rejected. HS* is rejected when a JWKS URL is set. |
| `HUMISENSE_AUTH_OIDC_HMAC_SECRET` | — | Symmetric secret. Only valid alongside an HS* algorithm and **without** a JWKS URL. |
| `HUMISENSE_AUTH_OIDC_TENANT_CLAIM` | — | Reserved for mapping a provider claim to tenant membership. |
| `HUMISENSE_AUTH_ALLOW_TENANT_HEADER_SELECTION` | `true` | Permit `X-Tenant-Id` to select among memberships the verified subject already holds. It can only select, never grant. |
| `HUMISENSE_AUTH_JWKS_CACHE_SECONDS` | `300` | JWKS cache lifetime. |
| `HUMISENSE_AUTH_LEEWAY_SECONDS` | `30` | Clock-skew tolerance for `exp` / `nbf`. |
| `HUMISENSE_BOOTSTRAP_TOKEN` | — | Break-glass: allows the first tenant and owner to be created with no principal. **Closes permanently** once a tenant exists, and **refuses to start in production**. |
| `HUMISENSE_METRICS_TOKEN` | — | Bearer token guarding `/metrics`. **Required in production.** |

### Example — Microsoft Entra ID

```bash
export HUMISENSE_AUTH_MODE=oidc
export HUMISENSE_AUTH_OIDC_ISSUER="https://login.microsoftonline.com/<tenant-id>/v2.0"
export HUMISENSE_AUTH_OIDC_AUDIENCE="api://<application-client-id>"
export HUMISENSE_AUTH_OIDC_JWKS_URL="https://login.microsoftonline.com/<tenant-id>/discovery/v2.0/keys"
export HUMISENSE_AUTH_OIDC_ALGORITHMS="RS256"
export HUMISENSE_METRICS_TOKEN="$(python -c 'import secrets;print(secrets.token_urlsafe(32))')"
```

### First-run provisioning

1. Set `HUMISENSE_BOOTSTRAP_TOKEN` to a strong random value.
2. `POST /api/v1/tenants` with header `X-Bootstrap-Token: <value>` and body
   `{"name": "...", "owner_email": "...", "owner_external_subject": "<idp-subject>"}`.
3. **Unset `HUMISENSE_BOOTSTRAP_TOKEN` and restart.** The bootstrap path is already closed
   by the existence of the tenant; removing the variable removes it from the environment.

## Backend — security

| Variable | Default | Purpose |
|---|---|---|
| `HUMISENSE_WEBHOOK_SIGNATURE_TOLERANCE_SECONDS` | `300` | Age window for a signed webhook delivery. |
| `HUMISENSE_CORS_ORIGINS` | `["http://localhost:5173"]` | Comma-separated or JSON list of allowed origins. |
| `HUMISENSE_RATE_LIMIT_DEFAULT_PER_MINUTE` | `120` | **Declared but not enforced** — see below. |

## Unused settings and absent controls

- `HUMISENSE_RATE_LIMIT_DEFAULT_PER_MINUTE` is defined in `config.py` but no code reads it.
  Application-level rate limiting is therefore **not implemented**; only provider-side 429
  handling exists (backoff and `Retry-After` respect in `app/core/http.py`).
- `HUMISENSE_AUTH_OIDC_TENANT_CLAIM` is reserved: no code reads it yet. Tenant membership is
  currently resolved from the `users` table, not from a provider claim.
- Row-level security is **not wired into the query path**. `tenant_session` in
  `app/db/session.py` exists but is never called, and there is no `app/db/rls.py`. Tenant
  isolation is enforced in the service layer and by principal resolution, and is covered by
  tests, but a database-level policy would be defence in depth. Tracked as a follow-up.
- The SQL adapter applies no statement timeout. It relies on executing against a read-only
  connection. A statement-timeout setting does not exist.
- The file adapter's permitted roots are **not** an environment variable. They are configured
  per connection in the adapter's `allowed_roots` list, and local file access is refused when
  that list is empty.
- No OAuth redirect-URI setting exists, because the interactive authorization-code flow is not
  implemented (see `AUDIT.md` §5). Layer 1 verifies tokens; it does not issue them.

## Frontend

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_BASE` | `/api/v1` | API base path. |
| `VITE_API_TARGET` | `http://localhost:8000` | Dev-server proxy target. |
| `VITE_TENANT_ID` | — | Development tenant identity. Production supplies identity from the authenticated session. |
| `VITE_USER_ID` | — | Development principal id. |
| `VITE_USER_ROLE` | `admin` | Development role. |

## Never place in these files

Provider tokens, OAuth client secrets, database passwords and webhook signing secrets belong
in the encrypted credential store or the deployment secret manager. They must never be
committed, placed in frontend variables, or written to logs.
