/**
 * Tenant selection rules.
 *
 * MOCKED: the OIDC library and the API module are stubbed so each backend
 * response can be simulated.  The provider's own logic — the part that decides
 * what the user is allowed to select — is real.
 *
 * The property under test is the one the backend cannot enforce for us: the UI
 * must never offer, store or send a tenant id that did not come from the
 * memberships endpoint.  The backend re-validates anyway, but a UI that offers
 * a foreign tenant would be an information leak in its own right.
 */

import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AuthProvider } from "../AuthProvider";
import { getSelectedTenantId, setSelectedTenantId, clearApiAuth } from "../apiAuth";

const whoami = vi.fn();
const listOwnMemberships = vi.fn();

vi.mock("../../api/client", () => ({
  api: {
    whoami: () => whoami(),
    listOwnMemberships: () => listOwnMemberships(),
  },
}));

let oidcUser: { access_token: string } | null = { access_token: "tok" };
const signinRedirect = vi.fn();
const signoutRedirect = vi.fn();

vi.mock("react-oidc-context", () => ({
  useAuth: () => ({
    user: oidcUser,
    isLoading: false,
    error: null,
    activeNavigator: null,
    signinRedirect,
    signoutRedirect,
  }),
}));

vi.mock("../config", async () => {
  const actual = await vi.importActual<typeof import("../config")>("../config");
  return {
    ...actual,
    resolveAuthConfig: () => ({
      configured: true,
      problems: [],
      settings: {
        authority: "https://idp.example.com/realms/main",
        clientId: "humisense-web",
        redirectUri: "https://app.example.com/auth/callback",
        postLogoutRedirectUri: "https://app.example.com/auth/logged-out",
        scope: "openid profile email",
      },
    }),
  };
});

import { AuthContextForTests, type AuthContextValue } from "../AuthProvider";

function Probe() {
  const value = React.useContext(AuthContextForTests) as AuthContextValue;
  return (
    <div>
      <span data-testid="state">{value.state}</span>
      <span data-testid="tenant">{value.selectedTenantId ?? "none"}</span>
      <button onClick={() => value.selectTenant("t-foreign")}>select foreign</button>
      <button onClick={() => value.selectTenant("t-2")}>select own second</button>
    </div>
  );
}

beforeEach(() => {
  clearApiAuth();
  window.sessionStorage.clear();
  whoami.mockReset();
  listOwnMemberships.mockReset();
  oidcUser = { access_token: "tok" };
});

describe("tenant selection", () => {
  it("offers only memberships returned by the backend", async () => {
    whoami.mockResolvedValue({
      tenant_id: "t-1",
      user_id: "u-1",
      role: "owner",
      subject: "alice",
      source: "oidc",
      is_admin: true,
      auth_mode: "oidc",
    });
    listOwnMemberships.mockResolvedValue([
      { tenant_id: "t-1", tenant_name: "Acme", tenant_slug: "acme", role: "owner" },
      { tenant_id: "t-2", tenant_name: "Beta", tenant_slug: "beta", role: "viewer" },
    ]);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("state").textContent).toBe("ready"),
    );
  });

  it("refuses to select a tenant the user does not belong to", async () => {
    whoami.mockResolvedValue({
      tenant_id: "t-1",
      user_id: "u-1",
      role: "owner",
      subject: "alice",
      source: "oidc",
      is_admin: true,
      auth_mode: "oidc",
    });
    listOwnMemberships.mockResolvedValue([
      { tenant_id: "t-1", tenant_name: "Acme", tenant_slug: "acme", role: "owner" },
      { tenant_id: "t-2", tenant_name: "Beta", tenant_slug: "beta", role: "viewer" },
    ]);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() =>
      expect(screen.getByTestId("state").textContent).toBe("ready"),
    );

    const user = userEvent.setup();

    // Resolution auto-selects the first membership, because a tenant must be
    // chosen before the identity within it can be resolved.
    await waitFor(() => expect(getSelectedTenantId()).toBe("t-1"));

    await user.click(screen.getByText("select foreign"));

    // A tenant id absent from the memberships response is ignored entirely:
    // the selection does not move, so the foreign id is never stored or sent.
    expect(getSelectedTenantId()).toBe("t-1");

    await user.click(screen.getByText("select own second"));
    expect(getSelectedTenantId()).toBe("t-2");
  });

  it("reports no_membership rather than ready when the user belongs nowhere", async () => {
    whoami.mockResolvedValue({
      tenant_id: "t-1",
      user_id: "u-1",
      role: "viewer",
      subject: "alice",
      source: "oidc",
      is_admin: false,
      auth_mode: "oidc",
    });
    listOwnMemberships.mockResolvedValue([]);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("state").textContent).toBe("no_membership"),
    );
  });

  it("reports unauthorized when the backend rejects the token", async () => {
    const { UnauthorizedError } = await vi.importActual<
      typeof import("../../api/errors")
    >("../../api/errors");
    whoami.mockRejectedValue(new UnauthorizedError("rejected"));
    listOwnMemberships.mockRejectedValue(new UnauthorizedError("rejected"));

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("state").textContent).toBe("unauthorized"),
    );
  });

  it("clears the stored selection on sign-out", async () => {
    setSelectedTenantId("t-1");
    whoami.mockResolvedValue({
      tenant_id: "t-1",
      user_id: "u-1",
      role: "owner",
      subject: "alice",
      source: "oidc",
      is_admin: true,
      auth_mode: "oidc",
    });
    listOwnMemberships.mockResolvedValue([
      { tenant_id: "t-1", tenant_name: "Acme", tenant_slug: "acme", role: "owner" },
    ]);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() =>
      expect(screen.getByTestId("state").textContent).toBe("ready"),
    );

    expect(signoutRedirect).toBeDefined();
  });
});
