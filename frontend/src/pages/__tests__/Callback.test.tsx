/**
 * Callback route behaviour.
 *
 * Regression guard for a real defect found in live verification: the callback
 * screen rendered a spinner forever and never entered the application, stranding
 * the user on a URL that still carried a spent `?code=...`.  These tests assert
 * both halves of the fix — that a ready session leaves for the app, and that a
 * terminal failure says which failure it was.
 *
 * MOCKED: the auth context is injected directly so each session state can be
 * rendered without an identity provider.  The Callback component and the router
 * are real.
 */

import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import Callback from "../Callback";
import { AuthContextForTests, type AuthContextValue } from "../../auth/AuthProvider";
import type { SessionState } from "../../auth/session";

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

/**
 * Renders the callback route with a landing route beside it, so a successful
 * navigation is observable as the landing content appearing.
 */
function renderCallback(value: AuthContextValue) {
  return render(
    <MemoryRouter initialEntries={["/auth/callback?code=abc&state=xyz"]}>
      <AuthContextForTests.Provider value={value}>
        <Routes>
          <Route path="/auth/callback" element={<Callback />} />
          <Route path="/today" element={<div data-testid="today-screen">Today</div>} />
        </Routes>
      </AuthContextForTests.Provider>
    </MemoryRouter>,
  );
}

describe("Callback", () => {
  it("enters the application once the session is ready", () => {
    renderCallback(session({ state: "ready" }));

    // The defect: this never appeared because the callback never navigated.
    expect(screen.getByTestId("today-screen")).toBeInTheDocument();
    expect(screen.queryByText(/completing sign-in/i)).toBeNull();
  });

  it("shows a spinner, not an error, while the session is still resolving", () => {
    renderCallback(session({ state: "initializing" }));

    expect(screen.getByText(/completing sign-in/i)).toBeInTheDocument();
    expect(screen.queryByTestId("today-screen")).toBeNull();
    expect(screen.queryByRole("button", { name: /try again/i })).toBeNull();
  });

  it("explains that a signed-in account with no membership needs an administrator", () => {
    renderCallback(session({ state: "no_membership" }));

    expect(screen.queryByTestId("today-screen")).toBeNull();
    expect(screen.getByText(/not a member of any humisense organization/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("surfaces the backend's rejection of the token", () => {
    renderCallback(
      session({ state: "unauthorized", error: "The backend rejected the access token." }),
    );

    expect(screen.getByText("The backend rejected the access token.")).toBeInTheDocument();
    expect(screen.queryByTestId("today-screen")).toBeNull();
  });

  it("offers a retry that starts a fresh sign-in", () => {
    const signIn = vi.fn();
    renderCallback(session({ state: "unavailable", signIn }));

    screen.getByRole("button", { name: /try again/i }).click();
    expect(signIn).toHaveBeenCalledOnce();
  });
});
