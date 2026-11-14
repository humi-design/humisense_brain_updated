/**
 * Section card.
 *
 * A titled container with an optional count and actions. Used by Today and by
 * the placeholder areas, so every section in the product has the same
 * hierarchy: title, description, then content.
 */

import type { ReactNode } from "react";
import type { LucideIcon } from "../ui/icons";

export function SectionCard({
  id,
  title,
  icon: Icon,
  description,
  count,
  actions,
  children,
}: {
  id?: string;
  title: string;
  icon?: LucideIcon;
  description?: ReactNode;
  count?: number;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="hs-card" id={id} aria-labelledby={id ? `${id}-title` : undefined}>
      <header className="hs-card-head">
        <div className="hs-card-head-main">
          {Icon && (
            <span className="hs-card-icon" aria-hidden="true">
              <Icon size={15} />
            </span>
          )}
          <div>
            <h3 className="hs-card-title" id={id ? `${id}-title` : undefined}>
              {title}
              {typeof count === "number" && (
                <span className="hs-card-count">{count}</span>
              )}
            </h3>
            {description && <p className="hs-card-desc">{description}</p>}
          </div>
        </div>
        {actions && <div className="hs-card-actions">{actions}</div>}
      </header>
      <div className="hs-card-body">{children}</div>
    </section>
  );
}
