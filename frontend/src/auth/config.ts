/**
 * OIDC configuration, parsed from Vite environment variables.
 *
 * Deliberately provider-agnostic: nothing here assumes Keycloak, Entra ID,
 * Okta or Auth0.  Any provider that publishes OIDC discovery at `authority`
 * works, which is why only the authority and client id are required.  Keycloak
 * appears in the documentation as a *local development example*, not as a
 * dependency.
 *
 * There is no client secret.  This is a public client using Authorization Code
 * with PKCE; a secret shipped to a browser is not a secret.
 */

/** Token storage is sessionStorage: see docs/FRONTEND_AUTH.md for the trade-off. */
export const TENANT_STORAGE_KEY = "humisense.tenant";
export const REAUTH_GUARD_KEY = "humisense.auth.reauth_attempted";

export interface OidcSettings {
  authority: string;
  clientId: string;
  redirectUri: string;
  postLogoutRedirectUri: string;
  scope: string;
  /** Discovery is used unless an explicit metadata URL is supplied. */
  metadataUrl?: string;
}

export interface AuthConfigResult {
  configured: boolean;
  settings: OidcSettings | null;
  /** Human-readable reasons the configuration is unusable. */
  problems: string[];
}

function env(name: keyof ImportMetaEnv): string {
  const value = import.meta.env[name];
  return typeof value === "string" ? value.trim() : "";
}

/**
 * Build the OIDC settings, or explain precisely what is missing.
 *
 * Returning problems rather than throwing keeps the app able to render an
 * honest "authentication is not configured" screen instead of a blank page.
 * It must never fall back to an unauthenticated mode.
 */
export function resolveAuthConfig(): AuthConfigResult {
  const authority = env("VITE_OIDC_AUTHORITY");
  const clientId = env("VITE_OIDC_CLIENT_ID");
  const problems: string[] = [];

  if (!authority) problems.push("VITE_OIDC_AUTHORITY is not set");
  if (!clientId) problems.push("VITE_OIDC_CLIENT_ID is not set");

  if (authority) {
    try {
      const parsed = new URL(authority);
      const local =
        parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1";
      if (parsed.protocol !== "https:" && !local) {
        problems.push(
          "VITE_OIDC_AUTHORITY must use https outside local development",
        );
      }
    } catch {
      problems.push("VITE_OIDC_AUTHORITY is not a valid URL");
    }
  }

  if (problems.length > 0) {
    return { configured: false, settings: null, problems };
  }

  // The redirect URI must match the provider registration byte for byte, so it
  // is derived from the running origin unless explicitly overridden.  The
  // override exists because the provider registration is the authority, not us.
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  const redirectUri = env("VITE_OIDC_REDIRECT_URI") || `${origin}/auth/callback`;
  const postLogoutRedirectUri =
    env("VITE_OIDC_POST_LOGOUT_REDIRECT_URI") || `${origin}/auth/logged-out`;

  return {
    configured: true,
    problems: [],
    settings: {
      authority,
      clientId,
      redirectUri,
      postLogoutRedirectUri,
      scope: env("VITE_OIDC_SCOPE") || "openid profile email",
      metadataUrl: env("VITE_OIDC_METADATA_URL") || undefined,
    },
  };
}

/** Where the provider sends the browser back after sign-out. */
export const LOGGED_OUT_PATH = "/auth/logged-out";
export const CALLBACK_PATH = "/auth/callback";
