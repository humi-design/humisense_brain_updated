# Prompt 01 — Design System & React Application Foundation

**Role:** Principal Frontend Architect / Design-System Engineer / React & TypeScript Engineer
**Date:** 2026-11-14
**Repository:** `humi-design/humisense_brain_updated`
**Base commit:** `ca4d6b0` (branch `milestone-0.5-frontend-auth`)
**Scope:** Build the design-system and React application shell that the rest of
Humisense Brain is written against, without regressing the working Layer 1
integration surfaces.

---

## 0. Headline

The Layer 1 screens existed and worked, but the application around them did not:
a single `App.tsx` rendered six integration pages with no navigation, no theme,
no shared component library and no product frame. There was no "Humisense" — there
was an integration dashboard.

This prompt delivers the foundation:

- a **token-based design system** (`--hs-*` semantic tokens, light + dark, no flash);
- a **component library** (Button, Badge, Card, Field, Tabs, domain badges, feedback
  states) with an explicit public surface;
- an **application shell** (sidebar, header, command palette, organization menu,
  skip link, mobile drawer) built on a single navigation source of truth;
- **product areas** — Today, Copilot, Missions, Workforce, Memory, Governance,
  Settings — each honest about whether its backend exists;
- the six **Layer 1 integration screens preserved** and re-mounted under `/apps`
  with their existing behaviour intact.

Everything the UI claims is read from the real API. Where a backend does not exist,
the screen says so and lists what it will do. Nothing is simulated.

---

## 1. What was already present

Verified against `ca4d6b0` before any change:

| Capability | State | Evidence |
|---|---|---|
| React 18 + Vite + TypeScript build | Working | `npm run build` produced a bundle |
| Six Layer 1 screens | Working | `Marketplace`, `ConnectionWizard`, `ConnectedSystems`, `Discovery`, `ConnectorStudio`, `HealthCentre` |
| Typed API client | Working | `src/api/client.ts`, `src/api/errors.ts` |
| OIDC authentication | Working | `OidcAuthProvider`, `AuthProvider`, `RequireAuth` (Milestone 0.5) |
| `useApi` data hook | Working | `src/lib/useApi.ts` |
| Backend Layer 1 API | Working, tested | 200 backend tests |
| **Application shell** | **Absent** | `App.tsx` rendered a bare page list |
| **Navigation** | **Absent** | No sidebar, no header, no palette |
| **Design tokens / theming** | **Absent** | Hard-coded colours in `styles.css` |
| **Component library** | **Minimal** | A single `components/ui.tsx` |
| **Product areas beyond Apps** | **Absent** | Today, Copilot, etc. did not exist |

The pre-existing `components/ui.tsx` and `App.tsx` were deleted and replaced by the
structured equivalents below. Every working screen and the API client were left in
place and unmodified except where noted in §3.

---

## 2. Design system

### 2.1 Tokens

`src/design-system/tokens/tokens.css` defines **145 semantic tokens** in two layers:

- `--hs-*` — the semantic tokens. All new code uses these.
- Legacy aliases (`--bg`, `--text`, `--accent`, …) that point at the semantic tokens,
  so the ~2,000 lines of existing Layer 1 page CSS became theme-aware without a rewrite.

Themes are selected by `[data-theme]` on `<html>`:

- `:root, [data-theme="light"]` — light (default)
- `[data-theme="dark"]` — dark

A **synchronous inline script in `index.html`** resolves the stored preference and sets
the attribute *before the bundle is parsed*, so there is no flash of the wrong theme.
The same logic lives in `ThemeProvider.tsx` and the two are kept in step.

Colour is never the only signal: every status carries text or an icon (see §5).

### 2.2 Component CSS

`src/design-system/tokens/components.css` holds **224 `.hs-*` component classes** —
shell, navigation, buttons, cards, tables, badges, tabs, settings, forms. Focus
affordances use a real, theme-aware ring (`--hs-focus-ring`), not a removed outline.
`prefers-reduced-motion` is honoured in three places.

### 2.3 Theme provider

`src/design-system/themes/ThemeProvider.tsx` exposes `useTheme()` with `preference`
(`light` / `dark` / `system`), the `resolved` theme, and `setPreference`. It persists to
`localStorage["humisense.theme"]` and listens to `prefers-color-scheme` while in
`system` mode.

### 2.4 Component library

`src/components/ui/` — public surface re-exported from `index.ts`:

| Export | Purpose |
|---|---|
| `Button`, `IconButton`, `ButtonRow` | Actions, with variants and sizes |
| `Badge` | Tone-based labels (always carry text) |
| `Card`, `CardHeader`, `CardBody`, `CardFooter` | Content containers |
| `Field`, `Input`, `Textarea`, `Select` | Labelled form controls |
| `Tabs` | Keyboard-navigable tab set |
| `StateBadge`, `StatusBadge`, `HealthDot`, `Stat` | Domain-specific status display |
| `Banner`, `Empty`, `ErrorNote`, `Loading` | Feedback primitives |
| `formatDate`, `relativeTime`, `initials`, `categoryLabel` | Formatting helpers |
| `icons` | A single Lucide-based icon module |

Icons are re-exported through `src/components/ui/icons.ts` so the icon library can be
swapped without touching call sites. `lucide-react` is the only new dependency.

---

## 3. Application shell and product areas

### 3.1 Shell

`src/app/` holds the frame:

- `AppProviders.tsx` — composes Theme, OIDC, Auth and Router providers.
- `AppShell.tsx` — sidebar + header + main region + mobile drawer.
- `routes.tsx` — the full route table.

Navigation has a **single source of truth**, `src/components/navigation/navConfig.ts`.
The sidebar, the mobile drawer and the command palette all read from it, so a route
cannot appear in one place and be missing from another. Areas whose backend does not
exist yet are flagged `pending` and render a "soon" marker.

`CommandPalette.tsx` is opened from the header button or ⌘K / Ctrl K, is fully
keyboard-driven, and lists only real destinations.

### 3.2 Product areas

| Area | Route | State |
|---|---|---|
| Today | `/today` | Real structure; sections explain they fill when Layer 2 publishes work |
| Copilot | `/copilot` | Planned area |
| Missions | `/missions` | Planned area |
| Workforce | `/workforce` | Planned area |
| Memory | `/memory` | Planned area |
| Governance | `/governance` | Planned area |
| Apps | `/apps` | **Real** — live counts from the Layer 1 API |
| Settings | `/settings` | Profile/Organization read real server values; Appearance works |

Planned areas share `src/features/PlannedArea.tsx`. Rather than five near-identical files
that drift apart, they supply their own copy and planned capabilities. The component
never renders sample records — it states the area is planned and names the layer that
will provide it.

### 3.3 Layer 1 screens

The six integration screens are unchanged and re-mounted under `/apps/*`
(`/apps/marketplace`, `/apps/connections`, `/apps/discovery`, `/apps/studio`,
`/apps/health`, `/apps/connections/new/:connectorId`). Legacy top-level paths
(`/marketplace`, `/discovery`, …) redirect to the new locations, preserving the query
string, so existing links and bookmarks keep working.

---

## 4. Fixes made during verification

### 4.1 Callback navigation (real defect)

**Symptom.** After a successful sign-in the callback screen rendered a spinner forever
and never entered the application, stranding the user on a URL that still carried a spent
`?code=...&state=...`.

**Cause.** `Callback` did not navigate on a resolved session.

**Fix.** `Callback.tsx` now navigates to `/today` with `replace` once `state === "ready"`
(so the spent code leaves history), renders `null` during the hand-off to avoid a flash,
and explains each terminal failure distinctly — "signed in but no membership" and "the
backend rejected the token" are different problems and now say so.

**Regression guard.** `src/pages/__tests__/Callback.test.tsx` (5 tests) asserts both
halves: a ready session leaves for the app, and a terminal failure names itself.

A duplicate-message defect (the problem text was rendered twice, once as a subtitle and
once in the card) was fixed in the same file.

### 4.2 Backend test hermeticity (real defect, found by cross-checking)

While verifying, `pytest` reported **20 failures** that did not reproduce in a clean
shell. Root cause: `backend/tests/conftest.py` used `os.environ.setdefault(...)`, and
pydantic-settings gives a real environment variable precedence over a model default.
Running the app requires `HUMISENSE_*` variables to be exported — so a developer with the
app's configuration in their shell silently reconfigured the tests (an exported
`HUMISENSE_AUTH_MODE=oidc` broke "header mode is the default").

Worse, with `HUMISENSE_DATABASE_URL` exported, the suite ran against the **development
database** and `drop_all`-ed every table. This destroyed the dev data during this session
and was recovered by re-seeding.

**Fix.** `conftest.py` now clears the `HUMISENSE_*` namespace and pins the values the
tests are written against. All 200 tests pass regardless of the developer's shell.

---

## 5. Accessibility

`src/app/__tests__/accessibility.test.tsx` (8 tests) is enforcement, not decoration. It
fails if a control loses its accessible name, if a status relies on colour alone, or if
the shell stops being keyboard navigable. It asserts:

- a skip link that becomes visible on focus, targeting the main region;
- every primary navigation link reachable by tabbing;
- the command palette opens from the header button;
- every interactive control in the shell has a name;
- the primary navigation landmark is labelled;
- the organization menu trigger is named;
- every badge tone carries a text label.

Focus is always visible (`--hs-focus-ring`); motion respects `prefers-reduced-motion`.

---

## 6. Verification

All commands run in this session, from `frontend/` unless noted.

| Check | Command | Result |
|---|---|---|
| Typecheck | `npm run typecheck` | `tsc --noEmit`, exit 0 |
| Frontend tests | `npx vitest run` | **91 passed** (11 files) |
| Production build | `npm run build` | built, no errors |
| Backend tests | `cd backend && .venv/bin/python -m pytest -q` | **200 passed** |
| Backend tests (leaky shell) | same, with `HUMISENSE_*` exported | **200 passed** (after the §4.2 fix) |

### 6.1 Live end-to-end verification

Verified against the running deployment
(`https://work-1-zoyufqrkjiatteme.prod-runtime.all-hands.dev`, OIDC at `work-2-…`) with a
real sign-in:

1. Cleared session storage and loaded `/today` → redirected to the provider.
2. Completed the sign-in form as `user-alice`.
3. Landed on `/today` with the full application shell — the §4.1 defect is fixed.
4. Confirmed the callback error path: `/auth/callback?code=spent&state=spent` shows
   "Sign-in could not be completed · No matching state found in storage" with a working
   **Try again** button, instead of hanging.
5. Marketplace renders **69 catalogued targets, 8 ready to connect**, each honestly
   labelled `planned` / `implemented` / `tested` / `integration verified`.
6. Discovery, Health Centre and the Universal Connector Studio render and read real data.
7. Theme toggled light → dark and back; `localStorage["humisense.theme"]` persisted and
   `data-theme` applied. Dark mode verified visually on the marketplace.

Screenshots (captured live, unedited) are in `backend/docs/screenshots/`:
`today-light.png`, `marketplace-dark.png`, `discovery.png`, `health-centre.png`,
`settings-appearance-light.png`, `settings-appearance-dark.png`.

---

## 7. What was changed

**Removed:** `src/App.tsx`, `src/components/ui.tsx` (superseded by `src/app/` and
`src/components/ui/`).

**Modified:** `src/main.tsx` (compose providers), `index.html` (theme bootstrap script),
`src/styles.css` (now theme-aware via token aliases), `src/pages/Callback.tsx` (fixes),
`package.json` (+ `lucide-react`), `backend/tests/conftest.py` (hermeticity).

**Added:** 44 source files — `src/design-system/`, `src/app/`, `src/components/{ui,layout,feedback,navigation}/`,
`src/features/`, `src/lib/format.ts`, `src/pages/NotFound.tsx`, and the new test files.

Nothing in the API client, the auth layer, or the six Layer 1 screens was changed except
the Callback fix. No backend security control was touched.

---

## 8. Known limitations and risks

- **React Router v7 future-flag warnings** appear in the test output. Non-blocking; they
  are deprecation notices for a future major version.
- **No visual-regression testing.** The design system is covered by unit and
  accessibility tests, not by screenshot diffing.
- **Planned areas have no backend.** Today/Copilot/Missions/Workforce/Memory/Governance
  render structure only. This is intentional and labelled in the UI; it is not a defect.
- **Theme preference is per-browser** (`localStorage`), not per-account, because there is
  no user-preferences backend yet.

---

## 9. Release recommendation

**PASS** for the design-system and application-foundation scope.

The deliverable is a real application frame around the existing, working Layer 1
surfaces. Every claim the UI makes is backed by the API; nothing is simulated. Two real
defects found during verification (callback navigation, test hermeticity) are fixed and
regression-guarded.

**Not claimed:** no new integration was verified against a live third-party provider in
this prompt. The integration status shown in the marketplace is exactly what Layer 1
recorded (`GitHub` integration-verified, `Slack` tested, `Canary Labs` implemented but
not verified against hardware).
