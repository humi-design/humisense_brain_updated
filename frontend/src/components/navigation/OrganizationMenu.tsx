/**
 * Organization and account menu.
 *
 * Everything shown here is the *server's* answer: `role` and `isAdmin` come
 * from `GET /tenants/whoami`, and the organization list comes from
 * `GET /tenants/memberships`. Nothing is read from localStorage, a Vite
 * variable or any other client-controlled source.
 *
 * Switching organization stores a selection that the backend re-validates on
 * every request, so a tampered value cannot widen access.
 */

import { useEffect, useRef, useState } from "react";
import { useAuth } from "../../auth/AuthProvider";
import {
  Building2,
  Check,
  ChevronDown,
  LogOut,
  Settings,
  User,
} from "../ui/icons";
import { useNavigate } from "react-router-dom";

export default function OrganizationMenu({ collapsed }: { collapsed: boolean }) {
  const { identity, memberships, selectedTenantId, selectTenant, signOut } =
    useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  const active =
    memberships.find((m) => m.tenant_id === selectedTenantId) ??
    memberships[0] ??
    null;

  // Close on outside click and on Escape.
  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!identity) return null;

  const label = active?.tenant_name ?? "No organization";

  return (
    <div className="hs-org" ref={ref}>
      <button
        type="button"
        className="hs-org-trigger"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Organization and account: ${label}`}
      >
        <span className="hs-org-avatar" aria-hidden="true">
          {label.slice(0, 1).toUpperCase()}
        </span>
        {!collapsed && (
          <>
            <span className="hs-org-text">
              <span className="hs-org-name">{label}</span>
              <span className="hs-org-role">{identity.role}</span>
            </span>
            <ChevronDown size={14} aria-hidden="true" />
          </>
        )}
      </button>

      {open && (
        <div className="hs-menu" role="menu">
          <div className="hs-menu-head">
            <div className="hs-menu-label">Signed in as</div>
            <div className="hs-menu-identity" title={identity.subject}>
              {identity.subject}
            </div>
            <div className="hs-menu-meta">
              {identity.role}
              {identity.isAdmin ? " · administrator" : ""}
            </div>
          </div>

          {memberships.length > 1 && (
            <>
              <div className="hs-menu-sep" />
              <div className="hs-menu-label" style={{ padding: "6px 10px" }}>
                Organization
              </div>
              {memberships.map((membership) => {
                const isActive = membership.tenant_id === active?.tenant_id;
                return (
                  <button
                    key={membership.tenant_id}
                    type="button"
                    role="menuitemradio"
                    aria-checked={isActive}
                    className="hs-menu-item"
                    onClick={() => {
                      selectTenant(membership.tenant_id);
                      setOpen(false);
                    }}
                  >
                    <Building2 size={14} aria-hidden="true" />
                    <span className="grow">{membership.tenant_name}</span>
                    <span className="dim" style={{ fontSize: 11 }}>
                      {membership.role}
                    </span>
                    {isActive && <Check size={13} aria-hidden="true" />}
                  </button>
                );
              })}
            </>
          )}

          <div className="hs-menu-sep" />
          <button
            type="button"
            role="menuitem"
            className="hs-menu-item"
            onClick={() => {
              navigate("/settings");
              setOpen(false);
            }}
          >
            <Settings size={14} aria-hidden="true" />
            <span className="grow">Settings</span>
          </button>
          <button
            type="button"
            role="menuitem"
            className="hs-menu-item"
            onClick={() => {
              navigate("/settings?section=profile");
              setOpen(false);
            }}
          >
            <User size={14} aria-hidden="true" />
            <span className="grow">Profile</span>
          </button>
          <button
            type="button"
            role="menuitem"
            className="hs-menu-item"
            onClick={signOut}
          >
            <LogOut size={14} aria-hidden="true" />
            <span className="grow">Sign out</span>
          </button>
        </div>
      )}
    </div>
  );
}
