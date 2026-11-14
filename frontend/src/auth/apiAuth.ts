/**
 * The bridge between the OIDC session and the API client.
 *
 * The API client must not import React, so the current access token and the
 * handlers for authorization failures live here instead of in a hook.  The
 * auth provider updates this module; `api/client.ts` reads it.
 *
 * No token is ever persisted here — the OIDC library owns storage.  This holds
 * the token for the lifetime of the page so a request can attach it
 * synchronously.
 */

import { TENANT_STORAGE_KEY } from "./config";

type TokenGetter = () => string | null;
type UnauthorizedHandler = () => void;

let getAccessToken: TokenGetter = () => null;
let onUnauthorized: UnauthorizedHandler = () => {};

/**
 * Whether a 401 has already been turned into a re-authentication attempt.
 *
 * This is *session* state, not per-request state: without it, an endpoint that
 * returns 401 for a reason the provider cannot fix would send the browser
 * through the login redirect on every request, forever.  It is reset whenever a
 * new session is registered, so a fresh token gets a fresh attempt.
 */
let reauthAttempted = false;

export function registerApiAuth(hooks: {
  getAccessToken: TokenGetter;
  onUnauthorized: UnauthorizedHandler;
}): void {
  getAccessToken = hooks.getAccessToken;
  onUnauthorized = hooks.onUnauthorized;
  reauthAttempted = false;
}

export function currentAccessToken(): string | null {
  return getAccessToken();
}

/**
 * Ask for re-authentication, at most once per session.
 *
 * Returns true if the request was made, so the caller can tell the difference
 * between "we are handling it" and "we already tried".
 */
export function requestReauthOnce(): boolean {
  if (reauthAttempted) return false;
  reauthAttempted = true;
  onUnauthorized();
  return true;
}

/** Called after a request succeeds, so a later 401 can be retried. */
export function markSessionHealthy(): void {
  reauthAttempted = false;
}

/** Reset to the inert defaults. Used by tests and on sign-out. */
export function clearApiAuth(): void {
  getAccessToken = () => null;
  onUnauthorized = () => {};
  reauthAttempted = false;
}

// -- tenant selection --------------------------------------------------------

/**
 * The tenant the user has chosen to work in.
 *
 * This is a *selection*, not a claim of authority: the backend re-resolves it
 * against the caller's verified memberships on every request and ignores it if
 * the subject does not hold that membership.  It is only ever set from the
 * response of `GET /tenants/memberships`.
 */
export function getSelectedTenantId(): string | null {
  try {
    return window.sessionStorage.getItem(TENANT_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setSelectedTenantId(tenantId: string | null): void {
  try {
    if (tenantId) window.sessionStorage.setItem(TENANT_STORAGE_KEY, tenantId);
    else window.sessionStorage.removeItem(TENANT_STORAGE_KEY);
  } catch {
    // Storage can be unavailable (private mode, disabled cookies). Losing the
    // selection is recoverable; the user simply chooses again.
  }
}
