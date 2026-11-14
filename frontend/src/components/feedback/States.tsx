/**
 * System states.
 *
 * Every data surface in the product resolves to one of these, so a section can
 * never silently render nothing. The distinction that matters most is between
 * "there is genuinely no data" (`Empty`) and "we could not load it"
 * (`ErrorState`) — showing an empty state for a failed request tells the user
 * their work is gone when it is not.
 *
 * Each state carries an icon and text, so meaning never depends on colour.
 */

import type { ReactNode } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Inbox,
  Loader2,
  Lock,
  PlugZap,
  Settings,
  ShieldAlert,
  WifiOff,
  type LucideIcon,
} from "../ui/icons";
import { Button } from "../ui/Button";

export interface StateAction {
  label: string;
  onClick: () => void;
}

interface StateShellProps {
  icon: LucideIcon;
  title: string;
  description?: ReactNode;
  action?: StateAction;
  secondaryAction?: StateAction;
  tone?: "neutral" | "warning" | "danger" | "info";
  compact?: boolean;
}

function StateShell({
  icon: Icon,
  title,
  description,
  action,
  secondaryAction,
  tone = "neutral",
  compact,
}: StateShellProps) {
  return (
    <div className={`hs-state hs-state-${tone}${compact ? " hs-state-compact" : ""}`}>
      <div className="hs-state-icon" aria-hidden="true">
        <Icon size={compact ? 16 : 20} />
      </div>
      <div className="hs-state-body">
        <p className="hs-state-title">{title}</p>
        {description && <div className="hs-state-desc">{description}</div>}
        {(action || secondaryAction) && (
          <div className="hs-btn-row" style={{ marginTop: 10 }}>
            {action && (
              <Button size="sm" variant="secondary" onClick={action.onClick}>
                {action.label}
              </Button>
            )}
            {secondaryAction && (
              <Button size="sm" variant="ghost" onClick={secondaryAction.onClick}>
                {secondaryAction.label}
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * There is genuinely no data. Never use this for a failed request.
 */
export function EmptyState({
  title = "Nothing here yet",
  description,
  action,
  compact,
}: {
  title?: string;
  description?: ReactNode;
  action?: StateAction;
  compact?: boolean;
}) {
  return (
    <StateShell
      icon={Inbox}
      title={title}
      description={description}
      action={action}
      compact={compact}
    />
  );
}

/**
 * A request failed. Distinct from empty on purpose.
 */
export function ErrorState({
  title = "Could not load this",
  description,
  action,
  compact,
}: {
  title?: string;
  description?: ReactNode;
  action?: StateAction;
  compact?: boolean;
}) {
  return (
    <StateShell
      icon={AlertTriangle}
      tone="danger"
      title={title}
      description={description}
      action={action}
      compact={compact}
    />
  );
}

/**
 * This area exists but its backend is not built yet.
 *
 * Honest by construction: it names the layer that will provide the data, so it
 * can never be mistaken for real customer data or for a loading failure.
 */
export function NotAvailableState({
  title = "Not available yet",
  description,
  compact,
}: {
  title?: string;
  description?: ReactNode;
  compact?: boolean;
}) {
  return (
    <StateShell
      icon={PlugZap}
      tone="info"
      title={title}
      description={description}
      compact={compact}
    />
  );
}

export function LoadingState({
  label = "Loading",
  rows = 3,
  compact,
}: {
  label?: string;
  rows?: number;
  compact?: boolean;
}) {
  return (
    <div
      className={`hs-skeleton-stack${compact ? " hs-skeleton-compact" : ""}`}
      role="status"
      aria-live="polite"
    >
      <span className="hs-visually-hidden">{label}</span>
      {Array.from({ length: rows }).map((_, index) => (
        <div
          key={index}
          className="hs-skeleton"
          style={{ width: `${94 - index * 11}%` }}
        />
      ))}
    </div>
  );
}

/** A single inline spinner for buttons and small surfaces. */
export function Spinner({ label = "Working" }: { label?: string }) {
  return (
    <span role="status" aria-live="polite">
      <span className="hs-visually-hidden">{label}</span>
      <Loader2 className="hs-spin" size={14} aria-hidden="true" />
    </span>
  );
}

export function OfflineState({
  description = "Humisense cannot reach the network. Work already loaded stays visible.",
  action,
}: {
  description?: ReactNode;
  action?: StateAction;
}) {
  return (
    <StateShell
      icon={WifiOff}
      tone="warning"
      title="You appear to be offline"
      description={description}
      action={action}
    />
  );
}

export function UnauthorizedState({
  description = "Your session has ended. Sign in again to continue.",
  action,
}: {
  description?: ReactNode;
  action?: StateAction;
}) {
  return (
    <StateShell
      icon={Lock}
      tone="warning"
      title="Session expired"
      description={description}
      action={action}
    />
  );
}

export function ForbiddenState({
  description = "You do not have permission to view this. Ask an administrator for access.",
  action,
}: {
  description?: ReactNode;
  action?: StateAction;
}) {
  return (
    <StateShell
      icon={ShieldAlert}
      tone="danger"
      title="Access denied"
      description={description}
      action={action}
    />
  );
}

export function NotConfiguredState({
  title = "Not configured",
  description,
  action,
}: {
  title?: string;
  description?: ReactNode;
  action?: StateAction;
}) {
  return (
    <StateShell
      icon={Settings}
      tone="info"
      title={title}
      description={description}
      action={action}
    />
  );
}

export function SuccessState({
  title,
  description,
}: {
  title: string;
  description?: ReactNode;
}) {
  return (
    <StateShell icon={CheckCircle2} tone="neutral" title={title} description={description} />
  );
}
