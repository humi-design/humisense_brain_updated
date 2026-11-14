/**
 * Domain badges and status indicators.
 *
 * These read Humisense's own vocabulary — implementation state and connection
 * status — and turn it into a tone. Keeping the mapping in one place means the
 * catalogue, the connected systems list and the health centre can never
 * disagree about what a given state looks like.
 *
 * Every badge carries its state as text, so the meaning survives without
 * colour.
 */

import type { ReactNode } from "react";
import type { ConnectionStatus, ImplementationState } from "../../api/client";
import { Badge, type BadgeTone } from "./Badge";

const STATE_TONE: Record<ImplementationState, BadgeTone> = {
  PLANNED: "neutral",
  SCAFFOLDED: "info",
  IMPLEMENTED: "accent",
  TESTED: "accent",
  INTEGRATION_VERIFIED: "success",
  PRODUCTION_READY: "success",
};

export function StateBadge({ state }: { state: ImplementationState }) {
  return (
    <Badge tone={STATE_TONE[state] ?? "neutral"}>
      {state.replace(/_/g, " ").toLowerCase()}
    </Badge>
  );
}

const CONNECTION_TONE: Record<ConnectionStatus, BadgeTone> = {
  catalogue_available: "neutral",
  installable: "neutral",
  configured: "info",
  authenticated: "info",
  connected: "accent",
  synchronizing: "accent",
  healthy: "success",
  degraded: "warning",
  disconnected: "neutral",
  revoked: "danger",
  failed: "danger",
};

export function StatusBadge({ status }: { status: ConnectionStatus }) {
  return <Badge tone={CONNECTION_TONE[status] ?? "neutral"}>{status}</Badge>;
}

/**
 * Health indicator.
 *
 * A dot alone would convey health by colour only, so this renders the dot
 * together with the status word.
 */
export function HealthDot({ status }: { status: string }) {
  const tone =
    status === "healthy"
      ? "success"
      : status === "degraded"
        ? "warning"
        : status === "unhealthy"
          ? "danger"
          : "neutral";
  return <Badge tone={tone}>{status}</Badge>;
}

export function Stat({ value, label }: { value: ReactNode; label: string }) {
  return (
    <div className="hs-stat">
      <span className="hs-stat-value">{value}</span>
      <span className="hs-stat-label">{label}</span>
    </div>
  );
}
