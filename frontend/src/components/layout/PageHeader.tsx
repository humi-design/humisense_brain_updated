/**
 * Page header.
 *
 * The single place page titles are styled, so hierarchy is consistent across
 * every area. Kept presentational: pages pass in what they need.
 */

import type { ReactNode } from "react";

export function PageHeader({
  title,
  description,
  meta,
  actions,
}: {
  title: string;
  description?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="hs-page-head">
      <div className="hs-page-head-main">
        <h1 className="hs-page-title">{title}</h1>
        {description && <p className="hs-page-desc">{description}</p>}
        {meta && <div className="hs-page-meta">{meta}</div>}
      </div>
      {actions && <div className="hs-page-actions">{actions}</div>}
    </div>
  );
}
