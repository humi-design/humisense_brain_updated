/**
 * Badge.
 *
 * A small status pill. Colour conveys tone but the label always carries the
 * meaning, so a colour-blind or screen-reader user gets the same information.
 */

import type { ReactNode } from "react";

export type BadgeTone =
  | "neutral"
  | "accent"
  | "success"
  | "warning"
  | "danger"
  | "info";

export function Badge({
  tone = "neutral",
  children,
  title,
}: {
  tone?: BadgeTone;
  children: ReactNode;
  title?: string;
}) {
  return (
    <span className={`hs-badge hs-badge-${tone}`} title={title}>
      {children}
    </span>
  );
}
