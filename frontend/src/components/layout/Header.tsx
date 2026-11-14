/**
 * Application header.
 *
 * Deliberately sparse: page title, command entry, notifications and the
 * organization menu (which lives in the sidebar on desktop). Everything else
 * belongs in the page, not in a global bar.
 */

import { useLocation } from "react-router-dom";
import { findNavItem } from "../navigation/navConfig";
import NotificationPanel from "../feedback/NotificationPanel";
import ThemeToggle from "./ThemeToggle";
import { Command, Menu, Search } from "../ui/icons";

interface HeaderProps {
  onOpenPalette: () => void;
  onOpenMobileNav: () => void;
}

/** Page titles that are not top-level navigation items. */
const EXTRA_TITLES: Record<string, string> = {
  "/settings": "Settings",
  "/apps/marketplace": "Integration Marketplace",
  "/apps/connections": "Connected Systems",
  "/apps/discovery": "Technology Discovery",
  "/apps/studio": "Universal Connector Studio",
  "/apps/health": "Integration Health Centre",
};

function titleFor(pathname: string): string {
  const exact = EXTRA_TITLES[pathname];
  if (exact) return exact;
  const nav = findNavItem(pathname);
  return nav?.label ?? "Humisense";
}

export default function Header({ onOpenPalette, onOpenMobileNav }: HeaderProps) {
  const location = useLocation();
  const title = titleFor(location.pathname);

  return (
    <header className="hs-header">
      <button
        type="button"
        className="hs-icon-btn hs-header-menu"
        onClick={onOpenMobileNav}
        aria-label="Open navigation"
      >
        <Menu size={18} aria-hidden="true" />
      </button>

      <span className="hs-header-title">{title}</span>

      <div className="hs-header-actions">
        <button
          type="button"
          className="hs-command-trigger"
          onClick={onOpenPalette}
          aria-label="Search and run commands"
        >
          <Search size={14} aria-hidden="true" />
          <span className="hs-command-trigger-text">Search or run a command</span>
          <kbd className="hs-kbd">
            <Command size={10} aria-hidden="true" />K
          </kbd>
        </button>

        <ThemeToggle />
        <NotificationPanel unavailable />
      </div>
    </header>
  );
}
