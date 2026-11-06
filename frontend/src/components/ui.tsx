/** Shared presentational components. */

import { type ReactNode } from "react";
import type { ConnectionStatus, ImplementationState } from "../api/client";

export function Badge({
  tone = "neutral",
  children,
}: {
  tone?: "neutral" | "success" | "warning" | "danger" | "info" | "accent";
  children: ReactNode;
}) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

const STATE_TONE: Record<ImplementationState, "neutral" | "success" | "warning" | "danger" | "info" | "accent"> = {
  PLANNED: "neutral",
  SCAFFOLDED: "info",
  IMPLEMENTED: "accent",
  TESTED: "accent",
  INTEGRATION_VERIFIED: "success",
  PRODUCTION_READY: "success",
};

export function StateBadge({ state }: { state: ImplementationState }) {
  const label = state.replace(/_/g, " ").toLowerCase();
  return <Badge tone={STATE_TONE[state] ?? "neutral"}>{label}</Badge>;
}

const CONNECTION_TONE: Record<ConnectionStatus, "neutral" | "success" | "warning" | "danger" | "info" | "accent"> = {
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

export function HealthDot({ status }: { status: string }) {
  const tone =
    status === "healthy" ? "var(--success)" : status === "degraded" ? "var(--warning)" : status === "unhealthy" ? "var(--danger)" : "var(--text-dim)";
  return <span className="dot" style={{ color: tone, display: "inline-block" }} />;
}

export function Stat({ value, label }: { value: ReactNode; label: string }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Banner({
  tone,
  children,
}: {
  tone: "info" | "warning" | "danger" | "success";
  children: ReactNode;
}) {
  return <div className={`banner banner-${tone}`}>{children}</div>;
}

export function Loading({ rows = 3 }: { rows?: number }) {
  return (
    <div className="stack" style={{ gap: 10 }}>
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="skeleton" style={{ width: `${90 - index * 12}%` }} />
      ))}
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof Error ? error.message : String(error);
  return <Banner tone="danger">{message}</Banner>;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function relativeTime(value: string | null | undefined): string {
  if (!value) return "never";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "never";
  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}

export function initials(text: string): string {
  return text
    .split(/[\s_-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export function categoryLabel(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}
