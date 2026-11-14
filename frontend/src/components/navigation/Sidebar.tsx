/**
 * Primary sidebar navigation.
 *
 * Desktop: a fixed column that collapses to an icon rail. The collapse state is
 * a layout preference, so it lives in localStorage and is applied to the shell
 * as a class rather than through a context, keeping re-renders local.
 *
 * Mobile/tablet: the same markup becomes an overlay drawer. Behaviour is driven
 * by the `isMobileOpen` prop the shell controls, so there is one navigation
 * definition rather than two.
 *
 * Organization and identity come from the server (see OrganizationMenu); this
 * file never derives them.
 */

import { NavLink } from "react-router-dom";
import { NAV_SECTIONS } from "./navConfig";
import { ChevronsLeft, ChevronsRight, X } from "../ui/icons";
import OrganizationMenu from "./OrganizationMenu";

interface SidebarProps {
  collapsed: boolean;
  onToggleCollapsed: () => void;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}

export default function Sidebar({
  collapsed,
  onToggleCollapsed,
  mobileOpen,
  onCloseMobile,
}: SidebarProps) {
  return (
    <>
      {/* Backdrop is only rendered on small screens, where the drawer floats. */}
      {mobileOpen && (
        <div
          className="hs-drawer-backdrop"
          onClick={onCloseMobile}
          aria-hidden="true"
        />
      )}

      <aside
        className={[
          "hs-sidebar",
          collapsed ? "is-collapsed" : "",
          mobileOpen ? "is-mobile-open" : "",
        ]
          .filter(Boolean)
          .join(" ")}
        aria-label="Primary"
      >
        <div className="hs-sidebar-head">
          <NavLink to="/today" className="hs-brand" aria-label="Humisense home">
            <span className="hs-brand-mark" aria-hidden="true">
              H
            </span>
            {!collapsed && (
              <span className="hs-brand-text">
                <span className="hs-brand-name">Humisense</span>
                <span className="hs-brand-sub">Brain</span>
              </span>
            )}
          </NavLink>

          <button
            type="button"
            className="hs-icon-btn hs-sidebar-close"
            onClick={onCloseMobile}
            aria-label="Close navigation"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>

        <nav className="hs-nav" aria-label="Primary">
          {NAV_SECTIONS.map((section) => (
            <div className="hs-nav-section" key={section.label}>
              {!collapsed && (
                <div className="hs-nav-section-label">{section.label}</div>
              )}
              {section.items.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={({ isActive }) =>
                      `hs-nav-item${isActive ? " is-active" : ""}`
                    }
                    title={collapsed ? item.label : undefined}
                    onClick={onCloseMobile}
                  >
                    <Icon size={16} aria-hidden="true" />
                    {!collapsed && <span>{item.label}</span>}
                    {!collapsed && item.pending && (
                      <span className="hs-nav-pending" title="Not built yet">
                        soon
                      </span>
                    )}
                  </NavLink>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="hs-sidebar-foot">
          <OrganizationMenu collapsed={collapsed} />

          <button
            type="button"
            className="hs-sidebar-collapse"
            onClick={onToggleCollapsed}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-expanded={!collapsed}
          >
            {collapsed ? (
              <ChevronsRight size={15} aria-hidden="true" />
            ) : (
              <>
                <ChevronsLeft size={15} aria-hidden="true" />
                <span>Collapse</span>
              </>
            )}
          </button>
        </div>
      </aside>
    </>
  );
}
