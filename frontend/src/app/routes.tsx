/**
 * Application routes.
 *
 * Structure:
 *   - provider landing pages (`/auth/*`) are reachable before a session exists
 *   - everything else is wrapped by `RequireAuth`, then the shell
 *   - the shell renders the product areas via <Outlet />
 *
 * The Layer 1 integration screens are mounted under `/apps` rather than
 * removed, so every existing authenticated route keeps working. The old
 * top-level paths redirect, so existing links and bookmarks do not break.
 */

import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import RequireAuth from "../auth/RequireAuth";
import AppShell from "./AppShell";

import Callback from "../pages/Callback";
import LoggedOut from "../pages/LoggedOut";

import Today from "../features/today/Today";
import Copilot from "../features/copilot/Copilot";
import Missions from "../features/missions/Missions";
import Workforce from "../features/workforce/Workforce";
import Memory from "../features/memory/Memory";
import Governance from "../features/governance/Governance";
import SettingsPage from "../features/settings/SettingsPage";

import Apps from "../features/apps/Apps";
import Marketplace from "../pages/Marketplace";
import ConnectedSystems from "../pages/ConnectedSystems";
import ConnectionWizard from "../pages/ConnectionWizard";
import Discovery from "../pages/Discovery";
import ConnectorStudio from "../pages/ConnectorStudio";
import HealthCentre from "../pages/HealthCentre";

import NotFound from "../pages/NotFound";

/** Preserves the query string when redirecting a legacy path. */
function RedirectWithQuery({ to }: { to: string }) {
  const location = useLocation();
  return <Navigate to={`${to}${location.search}`} replace />;
}

export default function AppRoutes() {
  return (
    <Routes>
      {/* Provider redirect landing pages. Reachable before a session exists. */}
      <Route path="/auth/callback" element={<Callback />} />
      <Route path="/auth/logged-out" element={<LoggedOut />} />

      {/* Everything else requires a session the backend has accepted. */}
      <Route
        path="/"
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/today" replace />} />

        <Route path="today" element={<Today />} />
        <Route path="copilot" element={<Copilot />} />
        <Route path="missions" element={<Missions />} />
        <Route path="workforce" element={<Workforce />} />
        <Route path="memory" element={<Memory />} />
        <Route path="governance" element={<Governance />} />
        <Route path="settings" element={<SettingsPage />} />

        {/* Apps: the Layer 1 integration surfaces, preserved intact. */}
        <Route path="apps" element={<Apps />} />
        <Route path="apps/marketplace" element={<Marketplace />} />
        <Route path="apps/connections" element={<ConnectedSystems />} />
        <Route
          path="apps/connections/new/:connectorId"
          element={<ConnectionWizard />}
        />
        <Route path="apps/discovery" element={<Discovery />} />
        <Route path="apps/studio" element={<ConnectorStudio />} />
        <Route path="apps/health" element={<HealthCentre />} />

        {/* Legacy top-level integration paths, kept so existing links work. */}
        <Route path="marketplace" element={<RedirectWithQuery to="/apps/marketplace" />} />
        <Route path="connections" element={<RedirectWithQuery to="/apps/connections" />} />
        <Route
          path="connections/new/:connectorId"
          element={<LegacyConnectionWizardRedirect />}
        />
        <Route path="discovery" element={<RedirectWithQuery to="/apps/discovery" />} />
        <Route path="studio" element={<RedirectWithQuery to="/apps/studio" />} />
        <Route path="health" element={<RedirectWithQuery to="/apps/health" />} />

        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

/** `/connections/new/:id` → `/apps/connections/new/:id`, preserving the id. */
function LegacyConnectionWizardRedirect() {
  const location = useLocation();
  const rest = location.pathname.replace(/^\/connections\/new\//, "");
  return <Navigate to={`/apps/connections/new/${rest}`} replace />;
}
