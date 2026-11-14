/**
 * The authenticated application shell.
 *
 * Rendered only once `RequireAuth` has established a `ready` session, so
 * nothing inside it can fetch with a token the backend has not accepted.
 *
 * Layout is CSS-driven: the sidebar collapse and mobile drawer are expressed as
 * classes on this element, so opening the drawer does not re-render the page
 * content inside <Outlet />.
 */

import { useCallback, useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import Sidebar from "../components/navigation/Sidebar";
import Header from "../components/layout/Header";
import CommandPalette, {
  useCommandPaletteShortcut,
} from "../components/navigation/CommandPalette";
import { SkipLink } from "../components/layout/SkipLink";

const COLLAPSE_KEY = "humisense.sidebar.collapsed";

function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(COLLAPSE_KEY) === "1";
  } catch {
    return false;
  }
}

export default function AppShell() {
  const [collapsed, setCollapsed] = useState<boolean>(readCollapsed);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const location = useLocation();

  const toggleCollapsed = useCallback(() => {
    setCollapsed((value) => {
      const next = !value;
      try {
        window.localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0");
      } catch {
        /* preference is best-effort */
      }
      return next;
    });
  }, []);

  const togglePalette = useCallback(() => setPaletteOpen((v) => !v), []);
  useCommandPaletteShortcut(togglePalette);

  // Close the mobile drawer whenever the route changes, so tapping a link does
  // not leave the drawer covering the destination.
  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  return (
    <div
      className={`hs-shell${collapsed ? " is-collapsed" : ""}`}
    >
      <SkipLink />
      <Sidebar
        collapsed={collapsed}
        onToggleCollapsed={toggleCollapsed}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />

      <div className="hs-main">
        <Header
          onOpenPalette={() => setPaletteOpen(true)}
          onOpenMobileNav={() => setMobileOpen(true)}
        />
        <main id="hs-content" className="hs-content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
      />
    </div>
  );
}
