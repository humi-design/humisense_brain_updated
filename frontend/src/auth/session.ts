/**
 * Session state, derived from the OIDC library plus the backend's view of us.
 *
 * Signing in is not the same as being *authorized*.  A user can hold a perfectly
 * valid token and still have no membership in any organization.  Treating that
 * as "logged in" produces an app that renders and then fails on every request,
 * so the two are separate states here.
 *
 * `ready` is only reached after `GET /tenants/whoami` has succeeded with a
 * bearer token — that is the proof that the token is accepted by the backend
 * and that the user can actually do something.
 */

export type SessionState =
  /** Configuration is missing or invalid; authentication cannot be attempted. */
  | "unconfigured"
  /** The OIDC library is still initialising. */
  | "initializing"
  /** No usable token; the user must sign in. */
  | "anonymous"
  /** A redirect callback is being processed. */
  | "signing_in"
  /** Token accepted, identity resolved, at least one membership. */
  | "ready"
  /** Token accepted, but the subject holds no membership anywhere. */
  | "no_membership"
  /** The token was rejected (expired, revoked, malformed). */
  | "unauthorized"
  /** The backend or provider could not be reached. */
  | "unavailable";

export interface ResolvedIdentity {
  tenantId: string;
  userId: string;
  role: string;
  subject: string;
  source: string;
  isAdmin: boolean;
  authMode: string;
}

export function isSignedIn(state: SessionState): boolean {
  return state === "ready" || state === "no_membership";
}
