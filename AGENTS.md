# AGENTS.md — Humisense Brain

## Repository layout

- `backend/` — FastAPI + SQLAlchemy + Pydantic. Tests: `backend/tests/`.
- `frontend/` — React + TypeScript + Vite. Tests: `frontend/src/**/__tests__/`.

## Commands

```bash
# Backend (from backend/)
. .venv/bin/activate
python -m pytest -q                      # full suite

# Frontend (from frontend/)
npm run typecheck
npm test
npm run build
```

## Authentication architecture (Milestone 0 / 0.5)

The backend resolves identity from a **verified bearer token only**. It never
trusts `X-Tenant-Id`, `X-User-Id` or `X-User-Role` from the client. Two auth
modes exist, selected by `HUMISENSE_AUTH_MODE`:

- `header` — development only; identity comes from headers.
- `oidc` — verifies a JWT against a trusted provider (`HUMISENSE_AUTH_OIDC_*`).

Frontend flow: `OidcAuthProvider` → `AuthProvider` (session state machine) →
`RequireAuth` route guard → pages. Tokens are attached by `src/api/client.ts`
via `src/auth/apiAuth.ts`.

### Endpoint sequencing (important)

`GET /tenants/memberships` is scoped to the caller's own verified subject and is
the **only** tenant endpoint reachable before a tenant is selected.
`GET /tenants/whoami` resolves the identity **within** a tenant and therefore
requires `X-Tenant-Id`. Call them in that order. Calling them in parallel, or
calling `whoami` first, yields a 403 that looks like an authorization failure
but is really a sequencing mistake.

### Tenant isolation in the UI

`AuthProvider.selectTenant` stores a tenant id only if it appears in the
memberships response. The stored value is re-validated on every resolution.
The backend re-validates independently, so a tampered client cannot widen access.

## Frontend architecture (Prompt 01)

The app is a product shell, not a page list. Structure:

- `src/design-system/` — `tokens/tokens.css` (semantic `--hs-*` tokens, light/dark via
  `[data-theme]` on `<html>`) and `tokens/components.css` (`.hs-*` classes).
  `themes/ThemeProvider.tsx` exposes `useTheme()`. `index.html` sets the theme
  synchronously before paint — keep it in step with the provider.
- `src/components/ui/` — component library. Import from the barrel `components/ui`,
  not from individual files.
- `src/components/{layout,navigation,feedback}/` — shell pieces. `navigation/navConfig.ts`
  is the single source of truth for nav (sidebar, drawer and palette all read it).
- `src/app/` — `AppProviders`, `AppShell`, `routes`. `src/features/` — product areas.

The six Layer 1 screens live in `src/pages/` and are mounted under `/apps/*`; legacy
top-level paths redirect there. Product areas with no backend use `features/PlannedArea.tsx`
and must never render sample records — they state the area is planned and name the layer
that will provide it.

## Testing notes

`backend/tests/conftest.py` clears the `HUMISENSE_*` namespace before importing settings.
This is deliberate: running the app requires those variables to be exported, and
pydantic-settings gives a real env var precedence over a model default. Do not switch it
back to `os.environ.setdefault` — an exported `HUMISENSE_DATABASE_URL` would point the
suite at the dev database and `drop_all` it.

Frontend tests are labelled with `MOCKED:` in the file header when a dependency is
injected. Keep that convention so a mocked pass is never mistaken for a verified
integration.

## Local OIDC testing

`ghcr.io/navikt/mock-oauth2-server` is used for end-to-end verification:

```bash
docker run -d --name humisense-idp -p 8081:8080 ghcr.io/navikt/mock-oauth2-server:2.1.10
```

Notes learned the hard way:

- The image **ignores a mounted `config.json`**; custom claims must be passed
  through the `JSON_CONFIG` environment variable, or by posting the sign-in
  form's `claims` field.
- By default the issued token has `aud` equal to the issuer id (`default`) and
  `sub` equal to the submitted username. Point `HUMISENSE_AUTH_OIDC_AUDIENCE`
  at the value the provider actually issues.
- `/authorize` renders an HTML sign-in form that must be POSTed with a
  `username` field; there is no auto-approve mode.

## Conventions

- Frontend CSS uses existing utility classes: `btn btn-primary`, `btn btn-ghost`,
  and `<dl class="kv">` for key/value blocks.
- `src/auth/apiAuth.ts` must stay React-free so the API client never imports React.
- Keep `frontend/.env*` out of version control; `.env.example` documents the vars.
