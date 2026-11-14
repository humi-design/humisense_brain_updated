/**
 * Identity and tenant switcher for the sidebar.
 *
 * Shows only what the server told us: the resolved role and the memberships it
 * returned.  The tenant list is never assembled from configuration, and the
 * switcher is hidden entirely when the user belongs to a single organization.
 */

import { useAuth } from "../auth/AuthProvider";

export default function IdentityPanel() {
  const { identity, memberships, selectedTenantId, selectTenant, signOut } =
    useAuth();

  if (!identity) return null;

  const active =
    memberships.find((m) => m.tenant_id === selectedTenantId) ??
    memberships[0] ??
    null;

  return (
    <div className="identity-panel">
      <div className="nav-group-label" style={{ padding: 0, marginBottom: 6 }}>
        Signed in
      </div>
      <div className="identity-subject" title={identity.subject}>
        {identity.subject}
      </div>
      <div className="dim" style={{ fontSize: 11, marginTop: 2 }}>
        {active ? active.tenant_name : "—"} · {identity.role}
      </div>

      {memberships.length > 1 && (
        <select
          className="select"
          style={{ marginTop: 8, width: "100%" }}
          value={active?.tenant_id ?? ""}
          onChange={(event) => selectTenant(event.target.value)}
          aria-label="Organization"
        >
          {memberships.map((membership) => (
            <option key={membership.tenant_id} value={membership.tenant_id}>
              {membership.tenant_name} ({membership.role})
            </option>
          ))}
        </select>
      )}

      <button
        className="btn btn-ghost"
        style={{ marginTop: 8, width: "100%" }}
        onClick={signOut}
      >
        Sign out
      </button>
    </div>
  );
}
