/**
 * Typed API client for Humisense Layer 1.
 *
 * The client never invents data: every value rendered in the UI comes from a
 * backend response.  Errors are surfaced verbatim (minus secrets) so the UI can
 * tell the truth about what is and is not connected.
 *
 * Authentication is a bearer token obtained by the OIDC provider.  The client
 * holds no identity of its own: the tenant is a *selection* the backend
 * re-validates, and the role is whatever the backend reports.
 */

import {
  ApiError,
  ForbiddenError,
  UnauthorizedError,
} from "./errors";
import {
  currentAccessToken,
  getSelectedTenantId,
  markSessionHealthy,
  requestReauthOnce,
} from "../auth/apiAuth";

export { ApiError, ForbiddenError, UnauthorizedError };

/** The server's answer to "who am I, and what may I do here?" */
export interface Identity {
  tenant_id: string;
  user_id: string;
  role: string;
  subject: string;
  source: string;
  is_admin: boolean;
  auth_mode: string;
}

/** One of the caller's own memberships, from `GET /tenants/memberships`. */
export interface OwnMembership {
  tenant_id: string;
  tenant_name: string;
  tenant_slug: string | null;
  role: string;
}

export type ImplementationState =
  | "PLANNED"
  | "SCAFFOLDED"
  | "IMPLEMENTED"
  | "TESTED"
  | "INTEGRATION_VERIFIED"
  | "PRODUCTION_READY";

export type ConnectionStatus =
  | "catalogue_available"
  | "installable"
  | "configured"
  | "authenticated"
  | "connected"
  | "synchronizing"
  | "healthy"
  | "degraded"
  | "disconnected"
  | "revoked"
  | "failed";

export interface ConnectorDefinition {
  connector_id: string;
  provider: string;
  display_name: string;
  category: string;
  description: string;
  version: string;
  auth_types: string[];
  capabilities: { capability: string; implementation_state?: string }[];
  required_scopes: string[];
  supported_resources: string[];
  implementation_state: ImplementationState;
  is_installable: boolean;
  supports_webhooks: boolean;
  supports_incremental: boolean;
  is_read_only: boolean;
  requires_on_premise: boolean;
  required_license: string | null;
  known_limitations: string[];
  documentation_url: string | null;
}

export interface Connection {
  connection_id: string;
  connector_id: string;
  provider: string;
  display_name: string;
  account_identifier: string | null;
  status: ConnectionStatus;
  health_status: string;
  health_checked_at: string | null;
  health_latency_ms: number | null;
  health_message: string | null;
  granted_scopes: string[];
  last_successful_sync: string | null;
  last_error: string | null;
  credential_reference_id: string | null;
  credential_rotated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConnectionResource {
  id: string;
  external_id: string;
  name: string;
  resource_type: string;
  parent_id: string | null;
  is_selected: boolean;
  read_only: boolean;
  metadata: Record<string, unknown>;
}

export interface TestConnectionResult {
  success: boolean;
  message: string;
  latency_ms: number | null;
  account_identifier: string | null;
  granted_scopes: string[];
  details: Record<string, unknown>;
}

export interface Assessment {
  assessment_id: string;
  application_name: string;
  vendor: string | null;
  category: string;
  discovery_source: string;
  integration_class: string;
  available_integration_method: string | null;
  authentication_requirements: string[];
  data_access_feasibility: string;
  read_capability: boolean;
  write_capability: boolean;
  required_permissions: string[];
  integration_risks: string[];
  implementation_estimate_days: number | null;
  status: ImplementationState;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface CustomDefinition {
  id: string;
  name: string;
  adapter_kind: string;
  version: number;
  definition: Record<string, unknown>;
  review_status: string;
  validation_report: { valid?: boolean; errors?: string[]; warnings?: string[] };
  created_at: string;
  updated_at: string;
}

export interface SyncRun {
  run_id: string;
  connection_id: string;
  resource_id: string | null;
  mode: string;
  status: string;
  records_fetched: number;
  records_written: number;
  records_skipped: number;
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface DeadLetter {
  id: string;
  connection_id: string;
  resource_id: string | null;
  reason: string;
  payload: Record<string, unknown>;
  resolved: boolean;
  created_at: string;
}

export interface AuditLog {
  id: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  actor_id: string | null;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface Health {
  status: string;
  version: string;
  database: string;
  connectors_registered: number;
  connectors_installable: number;
}

const API_BASE = import.meta.env.VITE_API_BASE || "/api/v1";

/**
 * Build the headers for one request.
 *
 * The only identity this client sends is a bearer token plus, optionally, the
 * tenant the user selected.  It never sends `X-User-Role` or `X-User-Id`: those
 * are not trusted by the backend in OIDC mode, and sending them would suggest
 * the UI has authority it does not have.  The role shown in the interface comes
 * from `whoami`, which is the server's answer, not the client's claim.
 */
function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const token = currentAccessToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const tenant = getSelectedTenantId();
  if (tenant) headers["X-Tenant-Id"] = tenant;
  return headers;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(init.headers || {}),
    },
  });
  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!response.ok) {
    const record = (body ?? {}) as Record<string, unknown>;
    const code = String(record.error ?? "request_failed");
    const message = String(
      record.message ?? `Request failed with status ${response.status}`,
    );
    if (response.status === 401) {
      // A rejected token is the one failure worth a retry through the provider.
      // `requestReauthOnce` allows a single attempt per session, so a provider
      // returning a token the backend keeps refusing cannot redirect forever.
      requestReauthOnce();
      throw new UnauthorizedError(message, record.detail);
    }
    if (response.status === 403) {
      throw new ForbiddenError(message, record.detail);
    }
    throw new ApiError(response.status, code, message, record.detail);
  }
  markSessionHealthy();
  return body as T;
}

export const api = {
  health: () => request<Health>("/health"),

  /** The server's resolved identity. The only trustworthy source of the role. */
  whoami: () => request<Identity>("/tenants/whoami"),

  /**
   * The caller's own memberships.
   *
   * This is the *only* source of tenant ids the UI may offer.  The backend
   * re-validates any selection on every subsequent request, so choosing from
   * this list is a convenience rather than a grant.
   */
  listOwnMemberships: () => request<OwnMembership[]>("/tenants/memberships"),

  listConnectors: (params?: { category?: string; search?: string; installable_only?: boolean }) => {
    const query = new URLSearchParams();
    if (params?.category) query.set("category", params.category);
    if (params?.search) query.set("search", params.search);
    if (params?.installable_only) query.set("installable_only", "true");
    const suffix = query.toString() ? `?${query}` : "";
    return request<ConnectorDefinition[]>(`/connectors${suffix}`);
  },
  getConnector: (id: string) => request<ConnectorDefinition>(`/connectors/${id}`),
  listCategories: () => request<string[]>("/connectors/categories"),

  listConnections: () => request<Connection[]>("/connections"),
  getConnection: (id: string) => request<Connection>(`/connections/${id}`),
  createConnection: (payload: {
    connector_id: string;
    display_name: string;
    configuration?: Record<string, unknown>;
    credentials?: Record<string, unknown>;
    granted_scopes?: string[];
  }) => request<Connection>("/connections", { method: "POST", body: JSON.stringify(payload) }),
  rotateCredentials: (id: string, credentials: Record<string, unknown>) =>
    request<Connection>(`/connections/${id}/credentials`, {
      method: "POST",
      body: JSON.stringify({ credentials }),
    }),
  testConnection: (id: string) =>
    request<TestConnectionResult>(`/connections/${id}/test`, { method: "POST" }),
  discoverResources: (id: string) =>
    request<ConnectionResource[]>(`/connections/${id}/resources`),
  selectResources: (id: string, external_ids: string[]) =>
    request<ConnectionResource[]>(`/connections/${id}/resources`, {
      method: "PUT",
      body: JSON.stringify({ external_ids }),
    }),
  configureSync: (
    id: string,
    payload: { mode?: string; page_size?: number; schedule_cron?: string | null; enabled?: boolean },
  ) =>
    request<Record<string, unknown>>(`/connections/${id}/sync-config`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  runSync: (id: string, resourceId?: string, mode?: string) => {
    const query = new URLSearchParams();
    if (resourceId) query.set("resource_id", resourceId);
    if (mode) query.set("mode", mode);
    const suffix = query.toString() ? `?${query}` : "";
    return request<SyncRun>(`/connections/${id}/sync${suffix}`, { method: "POST" });
  },
  listSyncRuns: (id: string) => request<SyncRun[]>(`/connections/${id}/sync-runs`),
  revokeConnection: (id: string) =>
    request<Connection>(`/connections/${id}/revoke`, { method: "POST" }),
  deleteConnection: (id: string) => request<void>(`/connections/${id}`, { method: "DELETE" }),

  listAssessments: () => request<Assessment[]>("/discovery/assessments"),
  createAssessment: (payload: Record<string, unknown>) =>
    request<Assessment>("/discovery/assessments", { method: "POST", body: JSON.stringify(payload) }),
  updateAssessment: (id: string, payload: Record<string, unknown>) =>
    request<Assessment>(`/discovery/assessments/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  importInventory: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    // Multipart: the browser sets Content-Type with the boundary, so only the
    // credential and tenant selection are added here.
    const response = await fetch(`${API_BASE}/discovery/inventory`, {
      method: "POST",
      headers: authHeaders(),
      body: form,
    });
    const text = await response.text();
    const body = text ? JSON.parse(text) : null;
    if (!response.ok) {
      const message = String(body?.message ?? "Inventory import failed");
      if (response.status === 401) throw new UnauthorizedError(message, body?.detail);
      if (response.status === 403) throw new ForbiddenError(message, body?.detail);
      throw new ApiError(
        response.status,
        String(body?.error ?? "import_failed"),
        message,
        body?.detail,
      );
    }
    return body as Assessment[];
  },

  listCustomDefinitions: () => request<CustomDefinition[]>("/custom-connectors"),
  validateCustomDefinition: (adapter_kind: string, definition: Record<string, unknown>) =>
    request<{ valid: boolean; errors: string[]; warnings: string[] }>(
      "/custom-connectors/validate",
      { method: "POST", body: JSON.stringify({ name: "validation", adapter_kind, definition }) },
    ),
  createCustomDefinition: (payload: {
    name: string;
    adapter_kind: string;
    definition: Record<string, unknown>;
    generated_by_ai?: boolean;
  }) =>
    request<CustomDefinition>("/custom-connectors", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  transitionCustomDefinition: (id: string, target: string) =>
    request<CustomDefinition>(`/custom-connectors/${id}/transition`, {
      method: "POST",
      body: JSON.stringify({ target }),
    }),
  listAdapterKinds: () => request<string[]>("/custom-connectors/adapter-kinds"),

  listDeadLetters: () => request<DeadLetter[]>("/dead-letters"),
  listAuditLogs: (action?: string) =>
    request<AuditLog[]>(`/audit-logs${action ? `?action=${action}` : ""}`),
  listOutbox: () => request<Record<string, unknown>[]>("/outbox"),
  eventContract: () =>
    request<{ schema_version: string; event_types: unknown[]; delivery: Record<string, unknown> }>(
      "/events/contract",
    ),
};
