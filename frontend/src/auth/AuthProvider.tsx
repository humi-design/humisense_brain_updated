/**
 * Authentication context for the whole application.
 *
 * Wraps `react-oidc-context` and adds the two things the library does not know
 * about: whether the *backend* accepts our token, and which tenant the user has
 * chosen.
 *
 * The distinction that matters: the library can report `isAuthenticated: true`
 * while the backend still refuses every request, because holding a valid token
 * and being a member of an organization are different facts.  This provider
 * resolves the second one before reporting the session as ready.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useAuth as useOidcAuth } from "react-oidc-context";
import { api, type OwnMembership } from "../api/client";
import { isForbidden, isUnauthorized } from "../api/errors";
import { resolveAuthConfig, REAUTH_GUARD_KEY } from "./config";
import {
  clearApiAuth,
  registerApiAuth,
  setSelectedTenantId,
  getSelectedTenantId,
} from "./apiAuth";
import type { ResolvedIdentity, SessionState } from "./session";

export interface AuthContextValue {
  state: SessionState;
  identity: ResolvedIdentity | null;
  memberships: OwnMembership[];
  selectedTenantId: string | null;
  /** Reasons the configuration is unusable, when `state === "unconfigured"`. */
  configProblems: string[];
  error: string | null;
  signIn: () => void;
  signOut: () => void;
  selectTenant: (tenantId: string) => void;
  /** Re-read identity and memberships after a tenant change or a failure. */
  refresh: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}

/**
 * Test-only: supply a session without running the OIDC redirect dance.
 *
 * Automated tests need to render protected screens without a provider.  This
 * is exported so tests can inject a fixed session; nothing in the application
 * uses it, and it cannot weaken the real provider because it only replaces
 * context values, never the API client's token source.
 */
export const AuthContextForTests = AuthContext;

export function AuthProvider({ children }: { children: ReactNode }) {
  const config = useMemo(() => resolveAuthConfig(), []);
  const oidc = useOidcAuth();

  const [identity, setIdentity] = useState<ResolvedIdentity | null>(null);
  const [memberships, setMemberships] = useState<OwnMembership[]>([]);
  const [selectedTenantId, setSelectedTenant] = useState<string | null>(
    getSelectedTenantId(),
  );
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const [resolving, setResolving] = useState(false);
  const [backendState, setBackendState] = useState<
    "unknown" | "ready" | "no_membership" | "unauthorized" | "unavailable"
  >("unknown");

  const refresh = useCallback(() => setNonce((value) => value + 1), []);

  // Hand the current token to the API client, and give it a way to ask for
  // re-authentication when the backend rejects it.
  useEffect(() => {
    registerApiAuth({
      getAccessToken: () => oidc.user?.access_token ?? null,
      onUnauthorized: () => {
        // One re-authentication attempt per session.  The guard lives in
        // sessionStorage so it survives the redirect; it is cleared as soon as
        // a request succeeds, so a later genuine expiry is still recoverable.
        try {
          if (window.sessionStorage.getItem(REAUTH_GUARD_KEY) === "1") return;
          window.sessionStorage.setItem(REAUTH_GUARD_KEY, "1");
        } catch {
          return;
        }
        void oidc.signinRedirect();
      },
    });
    return () => clearApiAuth();
  }, [oidc]);

  // Resolve the session whenever the token or the chosen tenant changes.
  //
  // Order matters. `GET /tenants/memberships` is the only endpoint reachable
  // *before* a tenant is selected — it is scoped to the caller's own verified
  // subject. `GET /tenants/whoami` resolves the identity *within* a tenant, so
  // it must be called only once a tenant has been chosen.  Calling them in
  // parallel, or calling `whoami` first, produces a 403 that looks like an
  // authorization failure but is really a sequencing mistake.
  useEffect(() => {
    if (!oidc.user?.access_token) {
      setIdentity(null);
      setMemberships([]);
      setBackendState("unknown");
      return;
    }
    let cancelled = false;
    setResolving(true);
    setError(null);

    (async () => {
      try {
        // Step 1: which organizations does this identity belong to?
        const own = await api.listOwnMemberships();
        if (cancelled) return;
        setMemberships(own);

        if (own.length === 0) {
          setIdentity(null);
          setBackendState("no_membership");
          return;
        }

        // Step 2: settle on a tenant. A stored selection is honoured only if
        // the backend still reports that membership; otherwise the first is
        // used. The stored value is never trusted on its own.
        const stored = getSelectedTenantId();
        const chosen = own.some((m) => m.tenant_id === stored)
          ? stored!
          : own[0].tenant_id;
        if (chosen !== stored) {
          setSelectedTenantId(chosen);
          setSelectedTenant(chosen);
        }

        // Step 3: resolve the identity within that tenant. `X-Tenant-Id` is
        // read from the selection by the API client, so this is the server's
        // answer for the tenant the user is actually working in.
        const who = await api.whoami();
        if (cancelled) return;
        setIdentity({
          tenantId: who.tenant_id,
          userId: who.user_id,
          role: who.role,
          subject: who.subject,
          source: who.source,
          isAdmin: who.is_admin,
          authMode: who.auth_mode,
        });
        setBackendState("ready");
        // A successful round trip clears the re-authentication loop guard.
        try {
          window.sessionStorage.removeItem(REAUTH_GUARD_KEY);
        } catch {
          /* storage unavailable; the guard simply stays unset */
        }
      } catch (err) {
        if (cancelled) return;
        if (isUnauthorized(err)) {
          setBackendState("unauthorized");
          setError("The backend rejected the access token.");
        } else if (isForbidden(err)) {
          // The token is valid but this identity may not use this tenant.
          // Treat it as no access rather than an error the user can retry.
          setBackendState("no_membership");
          setIdentity(null);
        } else {
          setBackendState("unavailable");
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (!cancelled) setResolving(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [oidc.user?.access_token, nonce]);

  const selectTenant = useCallback(
    (tenantId: string) => {
      // Only ids that came from the memberships response are ever stored.
      if (!memberships.some((m) => m.tenant_id === tenantId)) return;
      setSelectedTenantId(tenantId);
      setSelectedTenant(tenantId);
      refresh();
    },
    [memberships, refresh],
  );

  const signIn = useCallback(() => {
    void oidc.signinRedirect();
  }, [oidc]);

  const signOut = useCallback(() => {
    setSelectedTenantId(null);
    setSelectedTenant(null);
    setIdentity(null);
    setMemberships([]);
    clearApiAuth();
    void oidc.signoutRedirect();
  }, [oidc]);

  const state: SessionState = useMemo(() => {
    if (!config.configured) return "unconfigured";
    if (oidc.isLoading) return "initializing";
    if (oidc.error) return "unavailable";
    if (oidc.activeNavigator === "signinRedirect") return "signing_in";
    if (!oidc.user?.access_token) return "anonymous";
    if (resolving) return "initializing";
    if (backendState === "unauthorized") return "unauthorized";
    if (backendState === "unavailable") return "unavailable";
    if (backendState === "no_membership") return "no_membership";
    if (backendState === "ready") return "ready";
    return "initializing";
  }, [config.configured, oidc, resolving, backendState]);

  const value: AuthContextValue = {
    state,
    identity,
    memberships,
    selectedTenantId,
    configProblems: config.problems,
    error: error ?? (oidc.error ? oidc.error.message : null),
    signIn,
    signOut,
    selectTenant,
    refresh,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
