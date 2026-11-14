import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import Marketplace from "./pages/Marketplace";
import ConnectionWizard from "./pages/ConnectionWizard";
import ConnectedSystems from "./pages/ConnectedSystems";
import Discovery from "./pages/Discovery";
import ConnectorStudio from "./pages/ConnectorStudio";
import HealthCentre from "./pages/HealthCentre";
import Callback from "./pages/Callback";
import LoggedOut from "./pages/LoggedOut";
import RequireAuth from "./auth/RequireAuth";
import IdentityPanel from "./components/IdentityPanel";
import { useApi } from "./lib/useApi";
import { api } from "./api/client";

const NAV = [
  { group: "Integrations", items: [
    { to: "/marketplace", label: "Integration Marketplace" },
    { to: "/connections", label: "Connected Systems" },
  ]},
  { group: "Build", items: [
    { to: "/discovery", label: "Technology Discovery" },
    { to: "/studio", label: "Universal Connector Studio" },
  ]},
  { group: "Operate", items: [
    { to: "/health", label: "Integration Health Centre" },
  ]},
];

/**
 * The authenticated application shell.
 *
 * Rendered only once a session is ready, so nothing inside it can fetch with a
 * token that has not been accepted by the backend.
 */
function Shell() {
  const health = useApi(() => api.health(), []);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">H</div>
          <div>
            <div className="brand-text">Humisense</div>
            <div className="brand-sub">Layer 1 · Connected Apps</div>
          </div>
        </div>

        {NAV.map((group) => (
          <div key={group.group}>
            <div className="nav-group-label">{group.group}</div>
            {group.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
              >
                {item.label}
              </NavLink>
            ))}
          </div>
        ))}

        <div style={{ marginTop: "auto", padding: "14px 10px 4px" }}>
          <div className="nav-group-label" style={{ padding: 0, marginBottom: 6 }}>
            Platform
          </div>
          {health.data ? (
            <div className="stack" style={{ gap: 3 }}>
              <div className="row" style={{ fontSize: 11.5 }}>
                <span
                  className="dot"
                  style={{ color: health.data.status === "ok" ? "var(--success)" : "var(--warning)" }}
                />
                <span className="muted">
                  API {health.data.status} · v{health.data.version}
                </span>
              </div>
              <div className="dim" style={{ fontSize: 11 }}>
                {health.data.connectors_installable} of {health.data.connectors_registered} connectors
                installable
              </div>
            </div>
          ) : (
            <div className="dim" style={{ fontSize: 11 }}>
              {health.error ? "API unreachable" : "Connecting…"}
            </div>
          )}

          <IdentityPanel />
        </div>
      </aside>

      <main className="main">
        <Routes>
          <Route path="/" element={<Navigate to="/marketplace" replace />} />
          <Route path="/marketplace" element={<Marketplace />} />
          <Route path="/connections/new/:connectorId" element={<ConnectionWizard />} />
          <Route path="/connections" element={<ConnectedSystems />} />
          <Route path="/discovery" element={<Discovery />} />
          <Route path="/studio" element={<ConnectorStudio />} />
          <Route path="/health" element={<HealthCentre />} />
          <Route path="*" element={<Navigate to="/marketplace" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      {/* Provider redirect landing pages. Reachable before a session exists. */}
      <Route path="/auth/callback" element={<Callback />} />
      <Route path="/auth/logged-out" element={<LoggedOut />} />

      {/* Everything else requires a session the backend has accepted. */}
      <Route
        path="*"
        element={
          <RequireAuth>
            <Shell />
          </RequireAuth>
        }
      />
    </Routes>
  );
}
