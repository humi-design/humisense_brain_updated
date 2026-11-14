/**
 * Navigation, routing and shell tests.
 *
 * These cover the acceptance criteria in Prompt 01 Part 15: every primary
 * navigation link, active state, the default landing route, unknown routes,
 * deep links and the collapsed sidebar.
 */

import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { ThemeProvider } from "../../../design-system/themes/ThemeProvider";
import {
  AuthContextForTests,
  type AuthContextValue,
} from "../../../auth/AuthProvider";
import type { ResolvedIdentity, SessionState } from "../../../auth/session";
import type { OwnMembership } from "../../../api/client";
import AppShell from "../../../app/AppShell";
import AppRoutes from "../../../app/routes";
import { NAV_SECTIONS, ALL_NAV_ITEMS, findNavItem } from "../navConfig";

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
  {
    tenant_id: "t-1",
    tenant_name: "Acme Industrial",
    tenant_slug: "acme",
    role: "owner",
  },
];

function authValue(overrides: Partial<AuthContextValue> = {}): AuthContextValue {
  return {
    state: "ready" as SessionState,
    identity: IDENTITY,
    memberships: MEMBERSHIPS,
    selectedTenantId: "t-1",
    configProblems: [],
    error: null,
    signIn: () => {},
    signOut: () => {},
    selectTenant: () => {},
    refresh: () => {},
    ...overrides,
  };
}

/** Render the full routed application at a given path. */
function renderApp(path = "/today", auth: Partial<AuthContextValue> = {}) {
  return render(
    <ThemeProvider>
      <AuthContextForTests.Provider value={authValue(auth)}>
        <MemoryRouter initialEntries={[path]}>
          <AppRoutes />
        </MemoryRouter>
      </AuthContextForTests.Provider>
    </ThemeProvider>,
  );
}

/** Render just the shell, for tests about the chrome rather than routing. */
function renderShell(path = "/today") {
  return render(
    <ThemeProvider>
      <AuthContextForTests.Provider value={authValue()}>
        <MemoryRouter initialEntries={[path]}>
          <AppShell />
        </MemoryRouter>
      </AuthContextForTests.Provider>
    </ThemeProvider>,
  );
}

describe("navigation configuration", () => {
  it("defines every primary area exactly once", () => {
    const paths = ALL_NAV_ITEMS.map((i) => i.to);
    expect(new Set(paths).size).toBe(paths.length);
    expect(paths).toEqual(
      expect.arrayContaining([
        "/today",
        "/copilot",
        "/missions",
        "/workforce",
        "/memory",
        "/apps",
        "/governance",
      ]),
    );
  });

  it("gives every item an icon and a description", () => {
    for (const item of ALL_NAV_ITEMS) {
      expect(item.icon).toBeTruthy();
      expect(item.description.length).toBeGreaterThan(0);
    }
  });

  it("resolves nested paths to their owning section", () => {
    expect(findNavItem("/today")?.label).toBe("Today");
    expect(findNavItem("/apps/marketplace")?.label).toBe("Apps");
    expect(findNavItem("/nope")).toBeNull();
  });
});

describe("sidebar", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("renders every navigation link with its label", () => {
    renderShell();
    const nav = screen.getByRole("navigation", { name: "Primary" });
    for (const section of NAV_SECTIONS) {
      for (const item of section.items) {
        expect(
          within(nav).getByRole("link", { name: new RegExp(item.label) }),
        ).toBeInTheDocument();
      }
    }
  });

  it("marks the current route as active", () => {
    renderShell("/missions");
    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect(within(nav).getByRole("link", { name: /Missions/ })).toHaveClass(
      "is-active",
    );
    expect(within(nav).getByRole("link", { name: /Today/ })).not.toHaveClass(
      "is-active",
    );
  });

  it("collapses and persists the preference", async () => {
    const user = userEvent.setup();
    const { container } = renderShell();
    expect(container.querySelector(".hs-shell")).not.toHaveClass("is-collapsed");

    await user.click(screen.getByRole("button", { name: /collapse sidebar/i }));

    expect(container.querySelector(".hs-shell")).toHaveClass("is-collapsed");
    expect(window.localStorage.getItem("humisense.sidebar.collapsed")).toBe("1");
  });

  it("restores a collapsed sidebar from storage", () => {
    window.localStorage.setItem("humisense.sidebar.collapsed", "1");
    const { container } = renderShell();
    expect(container.querySelector(".hs-shell")).toHaveClass("is-collapsed");
  });
});

describe("routing", () => {
  it("lands on Today by default", () => {
    renderApp("/");
    expect(
      screen.getByRole("heading", { name: "Today", level: 1 }),
    ).toBeInTheDocument();
  });

  it("renders each primary area at its own route", () => {
    const cases: [string, string][] = [
      ["/today", "Today"],
      ["/copilot", "Copilot"],
      ["/missions", "Missions"],
      ["/workforce", "Workforce"],
      ["/memory", "Memory"],
      ["/governance", "Governance"],
      ["/settings", "Settings"],
    ];
    for (const [path, title] of cases) {
      const { unmount } = renderApp(path);
      expect(
        screen.getByRole("heading", { name: title, level: 1 }),
      ).toBeInTheDocument();
      unmount();
    }
  });

  it("shows a not-found page for an unknown route", () => {
    renderApp("/does-not-exist");
    expect(
      screen.getByRole("heading", { name: "Page not found", level: 1 }),
    ).toBeInTheDocument();
    expect(screen.getByText(/does not match anything/i)).toBeInTheDocument();
  });

  it("keeps provider callback routes reachable outside the shell", () => {
    renderApp("/auth/logged-out");
    // Not the shell: no primary navigation is rendered.
    expect(
      screen.queryByRole("navigation", { name: "Primary" }),
    ).not.toBeInTheDocument();
  });
});

/**
 * Deep links into the preserved Layer 1 screens.
 *
 * MOCKED: `fetch` returns fixed payloads so these tests exercise *routing*,
 * not the integration screens' data handling. The Layer 1 screens themselves
 * are unchanged and were verified against the real backend in Milestone 0.5.
 */
describe("Layer 1 deep links", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (url: string) => {
        const path = String(url);
        // Order matters: the single-connector path contains "/connectors/".
        const body = path.includes("/categories")
          ? []
          : path.includes("/connectors/")
            ? {
                connector_id: "github",
                provider: "github",
                display_name: "GitHub",
                category: "project_management",
                description: "GitHub repositories.",
                version: "1.0.0",
                auth_types: ["oauth2"],
                capabilities: [
                  { capability: "fetch_records", implementation_state: "TESTED" },
                ],
                required_scopes: [],
                supported_resources: [],
                implementation_state: "INTEGRATION_VERIFIED",
                is_installable: true,
                supports_webhooks: true,
                supports_incremental: true,
                is_read_only: false,
                requires_on_premise: false,
                required_license: null,
                known_limitations: [],
                documentation_url: null,
              }
            : path.includes("/connectors")
              ? []
              : path.includes("/connections")
                ? []
                : { status: "ok", version: "0.1.0", database: "ok" };
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("resolves the marketplace deep link", async () => {
    renderApp("/apps/marketplace");
    expect(
      await screen.findByRole("heading", {
        name: "Integration Marketplace",
        level: 1,
      }),
    ).toBeInTheDocument();
  });

  it("resolves the connected systems deep link", async () => {
    renderApp("/apps/connections");
    expect(
      await screen.findByRole("heading", { name: "Connected Systems", level: 1 }),
    ).toBeInTheDocument();
  });

  it("resolves the connector wizard deep link and keeps its parameter", async () => {
    renderApp("/apps/connections/new/github");
    expect(
      await screen.findByRole("heading", {
        name: "Connect GitHub",
        level: 1,
      }),
    ).toBeInTheDocument();
  });

  it("redirects a legacy /connections deep link to /apps/connections", async () => {
    renderApp("/connections");
    expect(
      await screen.findByRole("heading", { name: "Connected Systems", level: 1 }),
    ).toBeInTheDocument();
  });

  it("redirects a legacy wizard deep link and preserves the connector id", async () => {
    renderApp("/connections/new/github");
    expect(
      await screen.findByRole("heading", { name: "Connect GitHub", level: 1 }),
    ).toBeInTheDocument();
  });
});
