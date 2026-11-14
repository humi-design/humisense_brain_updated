/**
 * API client authentication behaviour.
 *
 * MOCKED: `fetch` is replaced with a stub so the client's request construction
 * can be inspected without a server.  The client itself is real.  The live
 * end-to-end proof against a real provider and backend is in
 * docs/FRONTEND_AUTH.md, not here.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ForbiddenError, UnauthorizedError } from "../client";
import { registerApiAuth, setSelectedTenantId, clearApiAuth } from "../../auth/apiAuth";

const TOKEN = "test-access-token";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  // A fresh Response per call: a body can only be read once.
  fetchMock = vi.fn().mockImplementation(async () => jsonResponse(200, {}));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  clearApiAuth();
});

function lastRequest(): { url: string; init: RequestInit } {
  const call = fetchMock.mock.calls.at(-1);
  if (!call) throw new Error("fetch was not called");
  return { url: String(call[0]), init: (call[1] ?? {}) as RequestInit };
}

function headersOf(init: RequestInit): Record<string, string> {
  return (init.headers ?? {}) as Record<string, string>;
}

describe("credential handling", () => {
  it("attaches a bearer token once one is available", async () => {
    registerApiAuth({ getAccessToken: () => TOKEN, onUnauthorized: () => {} });

    await api.whoami();

    expect(headersOf(lastRequest().init).Authorization).toBe(`Bearer ${TOKEN}`);
  });

  it("never sends X-User-Role or X-User-Id", async () => {
    registerApiAuth({ getAccessToken: () => TOKEN, onUnauthorized: () => {} });

    await api.listConnections();

    const headers = headersOf(lastRequest().init);
    expect(headers).not.toHaveProperty("X-User-Role");
    expect(headers).not.toHaveProperty("X-User-Id");
  });

  it("sends no Authorization header when there is no token", async () => {
    registerApiAuth({ getAccessToken: () => null, onUnauthorized: () => {} });

    await api.health();

    expect(headersOf(lastRequest().init)).not.toHaveProperty("Authorization");
  });

  it("sends only a tenant the caller selected, and only when selected", async () => {
    registerApiAuth({ getAccessToken: () => TOKEN, onUnauthorized: () => {} });

    await api.listConnections();
    expect(headersOf(lastRequest().init)).not.toHaveProperty("X-Tenant-Id");

    setSelectedTenantId("tenant-a");
    await api.listConnections();
    expect(headersOf(lastRequest().init)["X-Tenant-Id"]).toBe("tenant-a");
  });

  it("does not put the token in the URL or query string", async () => {
    registerApiAuth({ getAccessToken: () => TOKEN, onUnauthorized: () => {} });

    await api.whoami();

    const { url } = lastRequest();
    expect(url).not.toContain(TOKEN);
    expect(url).not.toContain("token=");
    expect(url).not.toContain("access_token");
  });
});

describe("failure mapping", () => {
  it("maps 401 to UnauthorizedError and asks for re-authentication once", async () => {
    const onUnauthorized = vi.fn();
    registerApiAuth({ getAccessToken: () => TOKEN, onUnauthorized });
    fetchMock.mockImplementation(async () => jsonResponse(401, { message: "nope" }));

    await expect(api.whoami()).rejects.toBeInstanceOf(UnauthorizedError);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("does not trigger repeated re-authentication attempts", async () => {
    const onUnauthorized = vi.fn();
    registerApiAuth({ getAccessToken: () => TOKEN, onUnauthorized });
    fetchMock.mockImplementation(async () => jsonResponse(401, { message: "nope" }));

    await expect(api.whoami()).rejects.toBeInstanceOf(UnauthorizedError);
    await expect(api.whoami()).rejects.toBeInstanceOf(UnauthorizedError);
    await expect(api.whoami()).rejects.toBeInstanceOf(UnauthorizedError);

    // The guard allows one attempt per page, not one per request: otherwise a
    // provider returning an unacceptable token would redirect forever.
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("maps 403 to ForbiddenError without asking for re-authentication", async () => {
    const onUnauthorized = vi.fn();
    registerApiAuth({ getAccessToken: () => TOKEN, onUnauthorized });
    fetchMock.mockImplementation(async () => jsonResponse(403, { message: "not allowed" }));

    await expect(api.listConnections()).rejects.toBeInstanceOf(ForbiddenError);
    // Signing in again cannot fix a permission problem.
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("surfaces the backend message for other failures", async () => {
    registerApiAuth({ getAccessToken: () => TOKEN, onUnauthorized: () => {} });
    fetchMock.mockImplementation(async () => jsonResponse(503, { message: "database down" }));

    await expect(api.health()).rejects.toThrow("database down");
  });
});

describe("identity endpoints", () => {
  it("reads identity from whoami, not from configuration", async () => {
    registerApiAuth({ getAccessToken: () => TOKEN, onUnauthorized: () => {} });
    fetchMock.mockResolvedValue(
      jsonResponse(200, {
        tenant_id: "t-1",
        user_id: "u-1",
        role: "viewer",
        subject: "alice",
        source: "oidc",
        is_admin: false,
        auth_mode: "oidc",
      }),
    );

    const identity = await api.whoami();

    expect(identity.role).toBe("viewer");
    expect(identity.tenant_id).toBe("t-1");
    expect(lastRequest().url).toContain("/tenants/whoami");
  });

  it("reads tenant choices from the memberships endpoint", async () => {
    registerApiAuth({ getAccessToken: () => TOKEN, onUnauthorized: () => {} });
    fetchMock.mockResolvedValue(
      jsonResponse(200, [
        { tenant_id: "t-1", tenant_name: "Acme", tenant_slug: "acme", role: "owner" },
      ]),
    );

    const memberships = await api.listOwnMemberships();

    expect(memberships).toHaveLength(1);
    expect(memberships[0].tenant_id).toBe("t-1");
    expect(lastRequest().url).toContain("/tenants/memberships");
  });
});
