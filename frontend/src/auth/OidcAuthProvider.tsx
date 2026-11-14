/**
 * Wires the OIDC library to the application.
 *
 * Kept separate from `AuthProvider` so the provider logic can be tested with an
 * injected context, while this file is the only place that knows about
 * `react-oidc-context`.
 *
 * Provider-agnostic: it is configured purely from `resolveAuthConfig()`.
 */

import { AuthProvider as OidcProvider } from "react-oidc-context";
import { WebStorageStateStore, type UserManagerSettings } from "oidc-client-ts";
import { resolveAuthConfig } from "./config";
import { AuthProvider } from "./AuthProvider";
import type { ReactNode } from "react";

/**
 * sessionStorage, not localStorage.
 *
 * The trade-off is documented in docs/FRONTEND_AUTH.md: sessionStorage limits
 * the window in which a token is exposed to a cross-site scripting flaw to a
 * single tab session, and it is not shared with other tabs or surviving browser
 * restarts.  It is not a defence against XSS itself — nothing available to a
 * browser script is.  Moving the token behind an HttpOnly cookie via a
 * backend-for-frontend is the documented hardening path.
 */
export function buildUserManagerSettings(): UserManagerSettings {
  const config = resolveAuthConfig();
  if (!config.configured || !config.settings) {
    // Callers must check `configured` first; this keeps the failure explicit.
    throw new Error(
      `Authentication is not configured: ${config.problems.join("; ")}`,
    );
  }
  const s = config.settings;
  return {
    authority: s.authority,
    client_id: s.clientId,
    redirect_uri: s.redirectUri,
    post_logout_redirect_uri: s.postLogoutRedirectUri,
    scope: s.scope,
    metadataUrl: s.metadataUrl,
    // Authorization Code + PKCE. No client secret: this is a public client.
    response_type: "code",
    // Tokens live for the tab session only.
    userStore: new WebStorageStateStore({ store: window.sessionStorage }),
    // No silent-renew iframe: it is unreliable under modern third-party cookie
    // restrictions and Safari's tracking prevention. Renewal happens through a
    // normal redirect when the token is rejected.
    automaticSilentRenew: false,
    monitorSession: false,
    loadUserInfo: false,
  };
}

export function AppAuthProvider({ children }: { children: ReactNode }) {
  const config = resolveAuthConfig();

  // Without configuration the OIDC provider cannot be constructed. The app
  // still renders so it can say so precisely, rather than showing a blank page.
  if (!config.configured || !config.settings) {
    return <AuthProvider>{children}</AuthProvider>;
  }

  return (
    <OidcProvider
      authority={config.settings.authority}
      client_id={config.settings.clientId}
      redirect_uri={config.settings.redirectUri}
      post_logout_redirect_uri={config.settings.postLogoutRedirectUri}
      scope={config.settings.scope}
      metadataUrl={config.settings.metadataUrl}
      response_type="code"
      userStore={new WebStorageStateStore({ store: window.sessionStorage })}
      automaticSilentRenew={false}
      monitorSession={false}
      loadUserInfo={false}
    >
      <AuthProvider>{children}</AuthProvider>
    </OidcProvider>
  );
}
