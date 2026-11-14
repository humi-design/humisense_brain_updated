/**
 * Auth configuration and tenant-selection behaviour.
 *
 * MOCKED: the environment is stubbed so misconfiguration can be exercised.
 * The parsing logic under test is real.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { resolveAuthConfig } from "../config";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("resolveAuthConfig", () => {
  it("reports what is missing instead of guessing", () => {
    vi.stubEnv("VITE_OIDC_AUTHORITY", "");
    vi.stubEnv("VITE_OIDC_CLIENT_ID", "");

    const result = resolveAuthConfig();

    expect(result.configured).toBe(false);
    expect(result.settings).toBeNull();
    expect(result.problems).toEqual(
      expect.arrayContaining([
        "VITE_OIDC_AUTHORITY is not set",
        "VITE_OIDC_CLIENT_ID is not set",
      ]),
    );
  });

  it("accepts a plain http authority only on localhost", () => {
    vi.stubEnv("VITE_OIDC_AUTHORITY", "http://idp.example.com/realms/main");
    vi.stubEnv("VITE_OIDC_CLIENT_ID", "humisense-web");

    const result = resolveAuthConfig();

    expect(result.configured).toBe(false);
    expect(result.problems.join(" ")).toContain("https");
  });

  it("accepts http on localhost for development", () => {
    vi.stubEnv("VITE_OIDC_AUTHORITY", "http://localhost:8080/realms/humisense");
    vi.stubEnv("VITE_OIDC_CLIENT_ID", "humisense-web");

    const result = resolveAuthConfig();

    expect(result.configured).toBe(true);
    expect(result.settings?.authority).toBe(
      "http://localhost:8080/realms/humisense",
    );
  });

  it("rejects an authority that is not a URL", () => {
    vi.stubEnv("VITE_OIDC_AUTHORITY", "not a url");
    vi.stubEnv("VITE_OIDC_CLIENT_ID", "humisense-web");

    const result = resolveAuthConfig();

    expect(result.configured).toBe(false);
    expect(result.problems.join(" ")).toContain("valid URL");
  });

  it("derives the redirect URI from the running origin by default", () => {
    vi.stubEnv("VITE_OIDC_AUTHORITY", "https://idp.example.com/realms/main");
    vi.stubEnv("VITE_OIDC_CLIENT_ID", "humisense-web");
    vi.stubEnv("VITE_OIDC_REDIRECT_URI", "");

    const result = resolveAuthConfig();

    expect(result.settings?.redirectUri).toBe(
      `${window.location.origin}/auth/callback`,
    );
  });

  it("honours an explicit redirect URI override", () => {
    // The provider registration is authoritative, so the deployment must be
    // able to state the URI exactly rather than have it inferred.
    vi.stubEnv("VITE_OIDC_AUTHORITY", "https://idp.example.com/realms/main");
    vi.stubEnv("VITE_OIDC_CLIENT_ID", "humisense-web");
    vi.stubEnv("VITE_OIDC_REDIRECT_URI", "https://app.example.com/auth/callback");

    const result = resolveAuthConfig();

    expect(result.settings?.redirectUri).toBe(
      "https://app.example.com/auth/callback",
    );
  });

  it("requests only the standard OIDC scopes by default", () => {
    vi.stubEnv("VITE_OIDC_AUTHORITY", "https://idp.example.com/realms/main");
    vi.stubEnv("VITE_OIDC_CLIENT_ID", "humisense-web");
    vi.stubEnv("VITE_OIDC_SCOPE", "");

    const result = resolveAuthConfig();

    expect(result.settings?.scope).toBe("openid profile email");
  });
});
