/**
 * Route guard behaviour.
 *
 * MOCKED: the auth context is supplied directly so each session state can be
 * rendered without an identity provider.  The guard component itself is real,
 * and these tests assert the security property that matters — an unauthenticated
 * or unauthorized session never reaches the application shell.
 */

import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import RequireAuth from "../RequireAuth";
import { AuthContextForTests, type AuthContextValue } from "../AuthProvider";
import type { SessionState } from "../session";

function session(overrides: Partial<AuthContextValue> = {}): AuthContextValue {
  return {
    state: "anonymous" as SessionState,
    identity: null,
    memberships: [],
    selectedTenantId: null,
    configProblems: [],
    error: null,
    signIn: vi.fn(),
    signOut: vi.fn(),
    selectTenant: vi.fn(),
    refresh: vi.fn(),
    ...overrides,
  };
}

function renderGuard(value: AuthContextValue) {
  return render(
    <MemoryRouter>
      <AuthContextForTests.Provider value={value}>
        <RequireAuth>
          <div data-testid="protected-shell">secret application content</div>
        </RequireAuth>
      </AuthContextForTests.Provider>
    </MemoryRouter>,
  );
}

describe("RequireAuth", () => {
  it("does not render the application for an anonymous session", () => {
    renderGuard(session({ state: "anonymous" }));

    expect(screen.queryByTestId("protected-shell")).toBeNull();
    expect(screen.getByText(/sign in to humisense/i)).toBeInTheDocument();
  });

  it("does not render the application while initializing", () => {
    renderGuard(session({ state: "initializing" }));

    expect(screen.queryByTestId("protected-shell")).toBeNull();
  });

  it("does not render the application when the token was rejected", () => {
    renderGuard(session({ state: "unauthorized", error: "token rejected" }));

    expect(screen.queryByTestId("protected-shell")).toBeNull();
    expect(screen.getByText("token rejected")).toBeInTheDocument();
  });

  it("does not render the application without a membership", () => {
    renderGuard(session({ state: "no_membership" }));

    expect(screen.queryByTestId("protected-shell")).toBeNull();
    expect(screen.getByText(/no organization access/i)).toBeInTheDocument();
  });

  it("does not render the application when authentication is unconfigured", () => {
    renderGuard(
      session({
        state: "unconfigured",
        configProblems: ["VITE_OIDC_AUTHORITY is not set"],
      }),
    );

    expect(screen.queryByTestId("protected-shell")).toBeNull();
    expect(screen.getByText("VITE_OIDC_AUTHORITY is not set")).toBeInTheDocument();
  });

  it("renders the application only for a ready session", () => {
    renderGuard(
      session({
        state: "ready",
        identity: {
          tenantId: "t-1",
          userId: "u-1",
          role: "owner",
          subject: "alice",
          source: "oidc",
          isAdmin: true,
          authMode: "oidc",
        },
        memberships: [
          { tenant_id: "t-1", tenant_name: "Acme", tenant_slug: "acme", role: "owner" },
        ],
        selectedTenantId: "t-1",
      }),
    );

    expect(screen.getByTestId("protected-shell")).toBeInTheDocument();
  });
});
