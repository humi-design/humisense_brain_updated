/**
 * Card primitives.
 *
 * Lower-level than SectionCard: Card is the container, the sub-parts are the
 * regions. Use SectionCard for a titled section with the standard heading
 * treatment; use these when a surface needs a custom layout.
 */

import type { ReactNode } from "react";

export function Card({
  children,
  className,
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "article";
}) {
  return <Tag className={`hs-card${className ? ` ${className}` : ""}`}>{children}</Tag>;
}

export function CardHeader({
  title,
  description,
  actions,
  level = 3,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  level?: 2 | 3 | 4;
}) {
  const Heading = `h${level}` as "h2" | "h3" | "h4";
  return (
    <div className="hs-card-head">
      <div className="hs-card-head-main">
        <div>
          <Heading className="hs-card-title">{title}</Heading>
          {description && <p className="hs-card-desc">{description}</p>}
        </div>
      </div>
      {actions && <div className="hs-card-actions">{actions}</div>}
    </div>
  );
}

export function CardBody({ children }: { children: ReactNode }) {
  return <div className="hs-card-body">{children}</div>;
}

export function CardFooter({ children }: { children: ReactNode }) {
  return <div className="hs-card-foot">{children}</div>;
}
