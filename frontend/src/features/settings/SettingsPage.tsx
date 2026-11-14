/**
 * Settings.
 *
 * The governing rule for this page: a setting is only shown as interactive if
 * it actually does something. Appearance works — it drives the real theme
 * provider. Profile and Organization display server-resolved values read-only.
 *
 * Sections with no backend are listed but explicitly marked as not yet
 * available, so nothing here appears to save and silently does nothing.
 */

import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useAuth } from "../../auth/AuthProvider";
import { PageHeader } from "../../components/layout/PageHeader";
import { SectionCard } from "../../components/layout/SectionCard";
import { NotAvailableState } from "../../components/feedback/States";
import {
  useTheme,
  type ThemePreference,
} from "../../design-system/themes/ThemeProvider";
import {
  Bell,
  Keyboard,
  Link2,
  Moon,
  Palette,
  Shield,
  Sun,
  User,
  Building2,
  Monitor,
} from "../../components/ui/icons";

const SECTIONS = [
  { id: "profile", label: "Profile", icon: User },
  { id: "appearance", label: "Appearance", icon: Palette },
  { id: "organization", label: "Organization", icon: Building2 },
  { id: "apps", label: "Connected applications", icon: Link2 },
  { id: "notifications", label: "Notifications", icon: Bell },
  { id: "security", label: "Security", icon: Shield },
  { id: "shortcuts", label: "Keyboard shortcuts", icon: Keyboard },
] as const;

type SectionId = (typeof SECTIONS)[number]["id"];

const THEME_OPTIONS: {
  value: ThemePreference;
  label: string;
  icon: typeof Sun;
  hint: string;
}[] = [
  { value: "light", label: "Light", icon: Sun, hint: "Always light" },
  { value: "dark", label: "Dark", icon: Moon, hint: "Always dark" },
  { value: "system", label: "System", icon: Monitor, hint: "Follow your device" },
];

const SHORTCUTS = [
  { keys: "⌘ K / Ctrl K", action: "Open the command palette" },
  { keys: "Esc", action: "Close the command palette or a dialog" },
  { keys: "↑ ↓", action: "Move through command results" },
  { keys: "Enter", action: "Run the highlighted command" },
  { keys: "Tab", action: "Move between controls" },
];

export default function SettingsPage() {
  const [params, setParams] = useSearchParams();
  const initial = (params.get("section") as SectionId) || "profile";
  const [active, setActive] = useState<SectionId>(
    SECTIONS.some((s) => s.id === initial) ? initial : "profile",
  );

  // Keep the URL in step so a settings section is linkable.
  useEffect(() => {
    if (params.get("section") !== active) {
      setParams({ section: active }, { replace: true });
    }
  }, [active, params, setParams]);

  return (
    <>
      <PageHeader
        title="Settings"
        description="Your preferences, and the details Humisense holds about you and your organization."
      />

      <div className="hs-settings">
        <nav className="hs-settings-nav" aria-label="Settings sections">
          {SECTIONS.map((section) => {
            const Icon = section.icon;
            return (
              <button
                key={section.id}
                type="button"
                className={`hs-settings-nav-item${active === section.id ? " is-active" : ""}`}
                onClick={() => setActive(section.id)}
                aria-current={active === section.id ? "true" : undefined}
              >
                <Icon size={15} aria-hidden="true" />
                <span>{section.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="hs-settings-body">
          {active === "profile" && <ProfileSection />}
          {active === "appearance" && <AppearanceSection />}
          {active === "organization" && <OrganizationSection />}
          {active === "apps" && (
            <SectionCard title="Connected applications" icon={Link2}>
              <p className="hs-muted" style={{ marginTop: 0 }}>
                Connections are managed in Apps, where you can see health,
                permissions and synchronization for each system.
              </p>
              <a className="hs-btn hs-btn-secondary hs-btn-sm" href="/apps/connections">
                <Link2 size={14} aria-hidden="true" />
                <span>Open Connected Systems</span>
              </a>
            </SectionCard>
          )}
          {active === "notifications" && (
            <SectionCard title="Notifications" icon={Bell}>
              <NotAvailableState
                compact
                title="Notification preferences are not available yet"
                description="Delivery channels and quiet hours arrive with the notification service. Nothing is configurable here yet."
              />
            </SectionCard>
          )}
          {active === "security" && (
            <SectionCard title="Security" icon={Shield}>
              <NotAvailableState
                compact
                title="Security settings are managed by your identity provider"
                description="Your session, password policy and multi-factor authentication are controlled by your organization's identity provider, not by Humisense."
              />
            </SectionCard>
          )}
          {active === "shortcuts" && (
            <SectionCard title="Keyboard shortcuts" icon={Keyboard}>
              <ul className="hs-shortcut-list">
                {SHORTCUTS.map((shortcut) => (
                  <li key={shortcut.keys}>
                    <kbd className="hs-kbd">{shortcut.keys}</kbd>
                    <span>{shortcut.action}</span>
                  </li>
                ))}
              </ul>
            </SectionCard>
          )}
        </div>
      </div>
    </>
  );
}

/** Read-only view of the server-resolved identity. */
function ProfileSection() {
  const { identity } = useAuth();

  return (
    <SectionCard
      title="Profile"
      icon={User}
      description="Read from the server. Humisense does not store its own copy of your identity."
    >
      {identity ? (
        <dl className="hs-kv">
          <dt>Subject</dt>
          <dd className="hs-mono">{identity.subject}</dd>
          <dt>Role</dt>
          <dd>{identity.role}</dd>
          <dt>Administrator</dt>
          <dd>{identity.isAdmin ? "Yes" : "No"}</dd>
          <dt>Identity source</dt>
          <dd>{identity.source}</dd>
        </dl>
      ) : (
        <NotAvailableState compact title="Identity not loaded" />
      )}
      <p className="hs-hint" style={{ marginTop: 12 }}>
        These values come from your identity provider and are resolved by the
        Humisense backend. They cannot be edited here.
      </p>
    </SectionCard>
  );
}

/** The one settings section that is fully functional. */
function AppearanceSection() {
  const { preference, resolved, setPreference } = useTheme();

  return (
    <SectionCard
      title="Appearance"
      icon={Palette}
      description="Choose how Humisense looks. This is saved to this browser only."
    >
      <div
        className="hs-theme-options"
        role="radiogroup"
        aria-label="Theme preference"
      >
        {THEME_OPTIONS.map((option) => {
          const Icon = option.icon;
          const selected = preference === option.value;
          return (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={selected}
              className={`hs-theme-option${selected ? " is-selected" : ""}`}
              onClick={() => setPreference(option.value)}
            >
              <Icon size={16} aria-hidden="true" />
              <span className="hs-theme-option-label">{option.label}</span>
              <span className="hs-theme-option-hint">{option.hint}</span>
            </button>
          );
        })}
      </div>

      <p className="hs-hint" style={{ marginTop: 12 }}>
        Currently showing the <strong>{resolved}</strong> theme
        {preference === "system" ? ", following your device." : "."}
      </p>
    </SectionCard>
  );
}

/** Read-only view of the caller's memberships. */
function OrganizationSection() {
  const { memberships, selectedTenantId, selectTenant, identity } = useAuth();

  return (
    <SectionCard
      title="Organization"
      icon={Building2}
      description="The organizations your identity belongs to, as reported by the server."
    >
      {memberships.length === 0 ? (
        <NotAvailableState
          compact
          title="No memberships"
          description="Your identity is not a member of any organization."
        />
      ) : (
        <ul className="hs-org-list">
          {memberships.map((membership) => {
            const isActive = membership.tenant_id === selectedTenantId;
            return (
              <li key={membership.tenant_id} className="hs-org-list-item">
                <span className="grow">
                  <span className="hs-org-list-name">{membership.tenant_name}</span>
                  <span className="hs-org-list-meta">
                    {membership.role}
                    {membership.tenant_slug ? ` · ${membership.tenant_slug}` : ""}
                  </span>
                </span>
                {isActive ? (
                  <span className="hs-org-list-current">Current</span>
                ) : (
                  <button
                    type="button"
                    className="hs-btn hs-btn-secondary hs-btn-sm"
                    onClick={() => selectTenant(membership.tenant_id)}
                  >
                    Switch
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {identity && (
        <p className="hs-hint" style={{ marginTop: 12 }}>
          You cannot change your own role or memberships. Those are administered
          by an organization administrator.
        </p>
      )}
    </SectionCard>
  );
}
