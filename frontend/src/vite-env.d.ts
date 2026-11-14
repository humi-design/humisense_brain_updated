/// <reference types="vite/client" />

/**
 * Build-time configuration.
 *
 * There is deliberately no tenant, user or role variable: identity comes from
 * the signed-in user's token, and the role is whatever the backend resolves.
 */
interface ImportMetaEnv {
  readonly VITE_API_BASE?: string;
  readonly VITE_API_TARGET?: string;

  /** OIDC provider. Required; the app refuses to sign in without them. */
  readonly VITE_OIDC_AUTHORITY?: string;
  readonly VITE_OIDC_CLIENT_ID?: string;

  /** Must match the provider registration exactly. Defaults to <origin>/auth/callback. */
  readonly VITE_OIDC_REDIRECT_URI?: string;
  readonly VITE_OIDC_POST_LOGOUT_REDIRECT_URI?: string;
  readonly VITE_OIDC_SCOPE?: string;
  readonly VITE_OIDC_METADATA_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
