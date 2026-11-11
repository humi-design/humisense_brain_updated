# Milestone 0 — Tenant Provisioning, Authentication and Authorization

**Role:** Senior Security Engineer / Backend Architect / Principal FastAPI Engineer
**Date:** 2026-11-11
**Repository:** `humisense_brain_updated`
**Base commit:** `92bf5e6` (branch `layer-1-connector-sensory-platform`)
**Scope:** Fix the two critical defects found in `AUDIT_00.md`, without weakening any
existing security control.

---

## 1. The two defects

`AUDIT_00.md` identified two defects that blocked any real deployment.

### Defect 1 — a fresh database cannot create its first connection

**Symptom.** With an empty database, `POST /api/v1/connections` fails with a foreign-key
error. Nothing in the API can create a `tenants` row, but `connections.tenant_id` is a
foreign key into `tenants`. A clean install is unusable.

**Cause.** There was no tenant-provisioning path at all. `tenants` was assumed to be
pre-populated out of band.

### Defect 2 — identity is client-supplied

**Symptom.** `X-Tenant-Id`, `X-User-Id` and `X-User-Role` were read straight from the
request and trusted. Any caller could set `X-Tenant-Id` to another organization's id and
`X-User-Role: owner`, and the API would act with those privileges. Tenant isolation
depended entirely on the client behaving itself.

**Cause.** No token verification existed. There was no cryptographic link between a
request and a real identity.

---

## 2. What was already present

Verified against `92bf5e6` before any change:

| Capability | State | Evidence |
|---|---|---|
| Credential encryption at rest | IMPLEMENTED | `app/core/crypto.py`, AES-GCM with tenant-bound associated data |
| Tenant-scoped queries | IMPLEMENTED | Services filter by `tenant_id`; `tests/test_tenant_isolation.py` |
| Webhook signature verification | TESTED | HMAC in `app/api/routers/webhooks.py` |
| SSRF / egress guarding | TESTED | `app/core/security.py`, `tests/test_security.py` |
| Audit log table | IMPLEMENTED | `app/db/models.py::AuditLog` |
| RLS helper functions | SCAFFOLDED (dead) | `app/db/session.py::tenant_session` — never called |
| Row-level security policies | PLANNED | No `app/db/rls.py`; docstring reference was stale |
| Token-based authentication | PLANNED | Did not exist |

The credential-encryption and SSRF controls were sound and were **not modified**. The
crypto module already bound ciphertext to `tenant_id`, which is why defect 2 was a
correctness failure rather than a data-disclosure failure: a cross-tenant read was blocked
by the API layer, and the ciphertext would not have decrypted for the wrong tenant anyway.

---

## 3. What was implemented

### 3.1 Token-based authentication (`app/core/identity.py`)

A single module converts a bearer token into trusted claims. It is the only place a token
is parsed, and it never takes a key, issuer, or algorithm from the request.

Verification performed on every token:

- signature, against the configured JWKS (fetched and cached by `PyJWKClient`);
- `alg` restricted to an explicit allow-list — `none` is never accepted;
- `iss` must equal the configured issuer exactly;
- `aud` must contain the configured audience;
- `exp` and `nbf` enforced, with configurable leeway;
- `sub` must be present and non-empty.

Every failure raises `TokenVerificationError` with a machine-readable reason. The reason is
logged server-side and **never** returned to the caller, so an attacker cannot probe the
configuration by comparing error messages.

### 3.2 Principal resolution (`app/api/deps.py`, rewritten)

Identity now comes from exactly one of two mutually exclusive sources.

**`oidc` mode (the only mode permitted outside development):**

1. The bearer token is verified.
2. The verified `(issuer, subject)` pair is looked up against `users` rows, joined to
   `tenants` and filtered on both being active.
3. Role and tenant come from that database row — never from the request.

A client cannot escalate. `X-User-Role` is ignored outright. `X-Tenant-Id` may only
*select* among memberships the verified subject already holds; it can never create or grant
one. An unknown tenant returns 403, not 404, so the response does not disclose whether the
tenant exists.

**`header` mode:** unchanged behaviour, but `Settings` now **refuses to start** unless the
environment is explicitly development or test. Header mode cannot run in production.

### 3.3 Tenant provisioning (`app/services/tenant_service.py`, `app/api/routers/tenants.py`)

Tenant creation is a transactional, audited operation with exactly two authorised routes:

- **Bootstrap** — only while the platform has *no tenants at all*, and only with the
  configured `HUMISENSE_BOOTSTRAP_TOKEN`. This exists so a clean install can be set up.
  It closes permanently the moment the first tenant exists. The setting is rejected in
  production at startup.
- **Administrator** — an authenticated `owner`/`admin` of an existing tenant.

There is no path by which an anonymous caller creates a tenant, and no path by which any
caller grants themselves a membership.

Also added: membership administration (add, list, activate/deactivate, link identity),
with two invariants enforced in the service layer — the last active owner of a tenant
cannot be deactivated, and one provider subject cannot be linked to two memberships in the
same tenant.

### 3.4 Database integrity (`alembic/versions/a1f0c2d4e5b6_...`)

The migration does three things, in this order:

1. Adds `external_issuer`, `external_subject`, `last_seen_at` to `users`.
2. **Backfills a `tenants` row for every `tenant_id` that already appears in tenant-scoped
   data but has no `tenants` row.** Without this, step 3 would fail on any existing
   deployment, because those rows already violate the foreign key they are about to gain.
3. Adds the missing `tenant_id → tenants.id` foreign keys, plus the indexes that make
   subject lookup efficient.

The backfill is non-destructive: it inserts only, never deletes or rewrites. Backfilled
tenants are named `Recovered organization (<id>)` so an administrator can find them. The
downgrade deliberately does **not** delete them — they may now be referenced by data that
predates the migration.

### 3.5 Metrics hardening

`/metrics` was world-readable. It now requires a bearer token when `HUMISENSE_METRICS_TOKEN`
is set, and that setting is mandatory in production.

### 3.6 Configuration hardening (`app/core/config.py`)

`Settings` validates the authentication configuration at startup and **fails closed**:

| Condition | Result |
|---|---|
| `auth_mode` not `oidc` or `header` | refuse to start |
| `header` mode outside development/test | refuse to start |
| `oidc` without issuer, audience, or key source | refuse to start |
| `oidc` with `none` in the algorithm list | refuse to start |
| `oidc` with an HS* algorithm **and** a JWKS URL | refuse to start |
| `oidc` with an HMAC secret but no HS* algorithm | refuse to start |
| `bootstrap_token` set in production | refuse to start |
| `metrics_token` unset in production | refuse to start |

The HS*-plus-JWKS rule matters: allowing a symmetric algorithm alongside a public JWKS is
the classic key-confusion attack, where an attacker signs a token with the public key as an
HMAC secret.

**A pre-existing bug was found and fixed while doing this.** The CSV validator for
`cors_origins`, `egress_allowed_hosts`, `egress_blocked_hosts` and `auth_oidc_algorithms`
was dead code: pydantic-settings JSON-decodes list fields *before* `mode="before"`
validators run, so `HUMISENSE_CORS_ORIGINS=a,b` raised `SettingsError` at startup. This
affected the existing egress controls, not just the new auth settings. The fields are now
annotated `NoDecode`, and the validator accepts both `a,b` and `["a","b"]` so existing
deployments using the JSON form keep working.

---

## 4. Test evidence

**185 tests pass** (`python -m pytest tests/ -q`), up from 105.

The new suites use real cryptography, not mocks:

| Suite | Tests | What it proves |
|---|---|---|
| `tests/test_auth_oidc.py` | 19 | Real RSA keys, real JWKS over real HTTP. Signature, issuer, audience, expiry, `nbf`, `alg=none`, HS256-confusion, unknown `kid`, malformed input — each rejected with the right reason. |
| `tests/test_authorization.py` | 14 | Header manipulation cannot escalate or impersonate. Cross-tenant read/delete/revoke returns 404 and leaves the row intact. Role enforcement on real endpoints. |
| `tests/test_provisioning.py` | 20 | Bootstrap token required, wrong token refused, bootstrap closes after first tenant, duplicate slug/email/role rejected, last owner protected, failure rolls back cleanly, and the previously-failing "provision then connect" sequence works. |
| `tests/test_auth_config.py` | 25 | Fail-closed startup for every unsafe configuration, plus the CSV-parsing regression. |
| `tests/test_tenant_isolation.py` | +2 | Header-mode role validation; missing tenant header refused. |

`tests/authkit.py` generates genuine RSA key pairs, signs tokens with the private half, and
serves a real JWKS document over HTTP. The production verification path runs end to end;
nothing in the security logic is stubbed.

### Live end-to-end verification

Run against a real `uvicorn` process, a fresh SQLite database migrated with Alembic, and a
real JWKS endpoint — not `TestClient`:

```
=== 1. no token -> 401 ===                        401
=== 2. malformed token -> 401 ===                 401
=== 3. bootstrap first tenant ===                 201
=== 4. valid token -> whoami ===                  200
      {"role":"owner","subject":"user-1","source":"oidc","is_admin":true}
=== 5. unknown subject -> 403 ===                 403
=== 6. X-User-Role: viewer + valid token ===      200, role resolved as "owner"
      (the header was ignored; the server used the database role)
=== 7. valid token creates a connection ===       201
=== 8. expired token -> 401 ===                   401
=== 9. wrong issuer -> 401 ===                    401
```

And the header-mode acceptance flow on a separate fresh database:

```
anonymous tenant creation      401
bootstrap with wrong token     401
bootstrap with correct token   201
bootstrap after tenant exists  401  (path closed)
create connection as owner     201  (previously impossible)
create connection as viewer    403
```

Production refusals, confirmed by starting the app:

```
prod + header mode    -> ConfigurationError: ... refused outside development/test
prod + bootstrap set  -> ConfigurationError: ... must not be set in production
```

---

## 5. Known limitations

These are stated plainly rather than hidden.

1. **Interactive OAuth authorization-code flow is not implemented.** Layer 1 verifies
   tokens that an identity provider issues; it does not itself run a login redirect, hold a
   session, or refresh tokens. A deployment needs an IdP (Entra ID, Okta, Keycloak, Auth0)
   and a frontend that obtains a token from it. This is the correct boundary for Layer 1,
   but it means the system is not "log in with a password" out of the box.

2. **Header mode still trusts headers when enabled.** It is confined to development and
   test, and refuses to start elsewhere, but it is not a secure mode and must never be
   enabled in a real environment. The `whoami` endpoint reports `auth_mode` so this is
   auditable.

3. **Row-level security is still not wired into the query path.** `tenant_session` in
   `app/db/session.py` remains unused. Tenant isolation is enforced by the service layer
   plus the new principal resolution, and is tested, but a database-level RLS policy would
   be defence in depth. This is deferred, not done.

4. **`/metrics` uses a static shared token**, not a scoped principal. Adequate for a
   scrape endpoint behind a private network; it is not per-tenant.

5. **No frontend changes.** The React app still reads `VITE_TENANT_ID` /
   `localStorage["humisense.tenant"]`. In OIDC mode the frontend must send a bearer token
   and drop those variables. That work belongs with the frontend milestone.

6. **The bootstrap token is a single shared secret.** Fine for first-run setup; it should
   be removed from the environment immediately afterwards. Production refuses to start
   while it is set, which forces that removal.

---

## 6. Required environment variables

### OIDC mode (production)

| Variable | Required | Notes |
|---|---|---|
| `HUMISENSE_AUTH_MODE` | yes | `oidc` |
| `HUMISENSE_AUTH_OIDC_ISSUER` | yes | Exact `iss` value, e.g. `https://login.microsoftonline.com/<tid>/v2.0` |
| `HUMISENSE_AUTH_OIDC_AUDIENCE` | yes | API audience or client id |
| `HUMISENSE_AUTH_OIDC_JWKS_URL` | yes\* | \*Or `HUMISENSE_AUTH_OIDC_HMAC_SECRET` with an HS* algorithm |
| `HUMISENSE_AUTH_OIDC_ALGORITHMS` | no | Default `RS256,ES256` |
| `HUMISENSE_METRICS_TOKEN` | yes in production | Guards `/metrics` |
| `HUMISENSE_CREDENTIAL_ENCRYPTION_KEY` | yes | 32-byte key, hex or base64 |
| `HUMISENSE_DATABASE_URL` | yes | PostgreSQL in production |

### Development

| Variable | Notes |
|---|---|
| `HUMISENSE_ENVIRONMENT` | `development` (default) or `test` |
| `HUMISENSE_AUTH_MODE` | `header` (default) |
| `HUMISENSE_BOOTSTRAP_TOKEN` | Set to create the first tenant, then unset |

Full reference: `docs/ENVIRONMENT.md`.

---

## 7. Database migration

```bash
cd backend
alembic upgrade head
```

Verified on SQLite in three scenarios: clean install, upgrade with orphan tenant data, and
downgrade then re-upgrade. All data preserved in each case.

---

## 8. API additions

| Method | Path | Authority |
|---|---|---|
| `GET` | `/api/v1/tenants/whoami` | any authenticated principal |
| `GET` | `/api/v1/tenants/bootstrap-status` | public |
| `POST` | `/api/v1/tenants` | bootstrap token, or tenant admin |
| `GET` | `/api/v1/tenants/{tenant_id}/memberships` | same tenant |
| `POST` | `/api/v1/tenants/{tenant_id}/memberships` | tenant admin |
| `POST` | `/api/v1/tenants/{tenant_id}/memberships/{id}/active` | tenant admin |
| `POST` | `/api/v1/tenants/{tenant_id}/memberships/{id}/link-identity` | tenant admin |

OpenAPI operations: 36 (was 35).

---

## 9. Release recommendation

**CONDITIONAL PASS.**

Both critical defects are fixed, verified by tests and by live runs. Nothing existing was
weakened; the credential-encryption and SSRF controls were untouched, and the migration
preserves all data.

The condition: **Layer 1 cannot be deployed to production until an OIDC provider is
configured and the frontend sends bearer tokens.** In OIDC mode the backend is complete and
fail-closed. Until the frontend stops sending `VITE_TENANT_ID`, a production deployment has
an authenticated backend and an unauthenticated UI — which is safe (every request is
rejected) but not usable.

Not claimed: no real identity provider was integrated end to end. The token path was
verified against a locally served JWKS using genuine RSA signatures, which exercises the
same code a real IdP would, but a live Entra ID / Okta round trip remains to be done.
