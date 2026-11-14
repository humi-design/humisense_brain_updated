/**
 * Inline feedback primitives.
 *
 * These are the small, in-context companions to the full-page states in
 * `components/feedback/States`. Use them inside tables, cards and forms where
 * a full state block would be too heavy.
 *
 * `Banner` carries an icon and a text label per tone, so a warning is never
 * communicated by colour alone.
 */

import type { ReactNode } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Info,
  Inbox,
  type LucideIcon,
} from "./icons";

type Tone = "info" | "warning" | "danger" | "success";

const TONE_ICON: Record<Tone, LucideIcon> = {
  info: Info,
  warning: AlertTriangle,
  danger: AlertTriangle,
  success: CheckCircle2,
};

/** Inline message. Announces politely so it is read without stealing focus. */
export function Banner({
  tone = "info",
  children,
}: {
  tone?: Tone;
  children: ReactNode;
}) {
  const Icon = TONE_ICON[tone];
  return (
    <div className={`hs-banner hs-banner-${tone}`} role="status">
      <Icon size={14} aria-hidden="true" />
      <div className="hs-banner-body">{children}</div>
    </div>
  );
}

/**
 * Inline "no rows" message.
 *
 * For a failed request use `ErrorNote` or `ErrorState` instead — an empty table
 * after an error tells the user their data is gone when it is not.
 */
export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="hs-empty">
      <Inbox size={18} aria-hidden="true" />
      <p>{children}</p>
    </div>
  );
}

/** Renders nothing when there is no error, so call sites stay uncluttered. */
export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof Error ? error.message : String(error);
  return <Banner tone="danger">{message}</Banner>;
}

/** Skeleton placeholder while a section loads. */
export function Loading({ rows = 3 }: { rows?: number }) {
  return (
    <div className="hs-skeleton-stack" role="status" aria-live="polite">
      <span className="hs-visually-hidden">Loading</span>
      {Array.from({ length: rows }).map((_, index) => (
        <div
          key={index}
          className="hs-skeleton"
          style={{ width: `${90 - index * 12}%` }}
        />
      ))}
    </div>
  );
}
