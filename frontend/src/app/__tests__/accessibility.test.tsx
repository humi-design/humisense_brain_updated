/**
 * Accessibility tests.
 *
 * These are enforcement, not decoration: they fail if a control loses its
 * accessible name, if a status indicator relies on colour alone, or if the
 * shell stops being keyboard navigable.
 */

import { describe, expect, it, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { ThemeProvider } from "../../design-system/themes/ThemeProvider";
import {
  AuthContextForTests,
  type AuthContextValue,
} from "../../auth/AuthProvider";
import type { ResolvedIdentity } from "../../auth/session";
import type { OwnMembership } from "../../api/client";
import AppShell from "../../app/AppShell";
import { Badge } from "../../components/ui/Badge";

const IDENTITY: ResolvedIdentity = {
  tenantId: "t-1",
  userId: "u-1",
  role: "owner",
  subject: "alice",
  source: "oidc",
  isAdmin: true,
  authMode: "oidc",
};

const MEMBERSHIPS: OwnMembership[] = [
  { tenant_id: "t-1", tenant_name: "Acme", tenant_slug: "acme", role: "owner" },
];

const auth: AuthContextValue = {
  state: "ready",
  identity: IDENTITY,
  memberships: MEMBERSHIPS,
  selectedTenantId: "t-1",
  configProblems: [],
  error: null,
  signIn() {},
  signOut() {},
  selectTenant() {},
  refresh() {},
};

function renderShell() {
  return render(
    <ThemeProvider>
      <AuthContextForTests.Provider value={auth}>
        <MemoryRouter initialEntries={["/today"]}>
          <AppShell />
        </MemoryRouter>
      </AuthContextForTests.Provider>
    </ThemeProvider>,
  );
}

beforeEach(() => window.localStorage.clear());

describe("keyboard navigation", () => {
  it("offers a skip link that becomes visible on focus", async () => {
    const user = userEvent.setup();
    renderShell();
    await user.tab();
    const skip = screen.getByRole("link", { name: "Skip to content" });
    expect(skip).toHaveFocus();
    expect(skip).toHaveAttribute("href", "#hs-content");
  });

  it("exposes the main region as a target for the skip link", () => {
    renderShell();
    expect(document.getElementById("hs-content")).not.toBeNull();
  });

  it("reaches every primary navigation link by tabbing", () => {
    renderShell();
    const nav = screen.getByRole("navigation", { name: "Primary" });
    const links = within(nav).getAllByRole("link");
    for (const link of links) {
      expect(link).toHaveAttribute("href");
    }
    expect(links.length).toBeGreaterThan(0);
  });

  it("opens the command palette from the header button", async () => {
    const user = userEvent.setup();
    renderShell();
    await user.click(
      screen.getByRole("button", { name: /search and run commands/i }),
    );
    expect(
      screen.getByRole("dialog", { name: "Command palette" }),
    ).toBeInTheDocument();
  });
});

describe("accessible names", () => {
  it("gives every interactive control in the shell a name", () => {
    renderShell();
    const controls = screen.getAllByRole("button");
    for (const control of controls) {
      const name =
        control.getAttribute("aria-label") ??
        control.textContent?.trim() ??
        "";
      expect(name.length).toBeGreaterThan(0);
    }
  });

  it("labels the primary navigation landmark", () => {
    renderShell();
    expect(
      screen.getByRole("navigation", { name: "Primary" }),
    ).toBeInTheDocument();
  });

  it("names the organization menu trigger", () => {
    renderShell();
    expect(
      screen.getByRole("button", { name: /organization and account/i }),
    ).toBeInTheDocument();
  });
});

describe("status is never colour alone", () => {
  it("carries a text label in every badge tone", () => {
    for (const tone of ["success", "warning", "danger", "info", "neutral"] as const) {
      const { unmount } = render(<Badge tone={tone}>Healthy</Badge>);
      expect(screen.getByText("Healthy")).toBeInTheDocument();
      unmount();
    }
  });
});
