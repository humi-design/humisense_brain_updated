/**
 * Shared shell for areas whose backend does not exist yet.
 *
 * Copilot, Missions, Workforce, Memory and Governance are all in this position
 * in this milestone. Rather than five near-identical files that drift apart,
 * they share this component and supply only their own copy and planned
 * capabilities.
 *
 * The component is explicit that the area is *planned*: it lists what it will
 * do and states which layer provides it. It never renders sample records.
 */

import type { ReactNode } from "react";
import { PageHeader } from "../components/layout/PageHeader";
import { SectionCard } from "../components/layout/SectionCard";
import { NotAvailableState } from "../components/feedback/States";
import { Clock, type LucideIcon } from "../components/ui/icons";

export interface PlannedCapability {
  title: string;
  description: string;
}

export function PlannedArea({
  title,
  description,
  icon,
  layer,
  summary,
  capabilities,
  footer,
}: {
  title: string;
  description: string;
  icon: LucideIcon;
  /** The layer that will provide this area's data. */
  layer: string;
  /** One paragraph on what the area will do once built. */
  summary: ReactNode;
  capabilities: PlannedCapability[];
  footer?: ReactNode;
}) {
  return (
    <>
      <PageHeader title={title} description={description} />

      <div className="hs-notice" role="note">
        <Clock size={15} aria-hidden="true" />
        <div>
          <strong>Planned — not built yet.</strong>
          <p>{summary}</p>
        </div>
      </div>

      <SectionCard
        id={`${title.toLowerCase()}-capabilities`}
        title="What this area will do"
        icon={icon}
        description={`Provided by ${layer}.`}
      >
        <ul className="hs-capability-list">
          {capabilities.map((capability) => (
            <li key={capability.title}>
              <span className="hs-capability-title">{capability.title}</span>
              <span className="hs-capability-desc">{capability.description}</span>
            </li>
          ))}
        </ul>
      </SectionCard>

      <SectionCard title="Current state" icon={Clock}>
        <NotAvailableState
          compact
          title="No backend for this area yet"
          description={`The interface is in place. Data arrives when ${layer} is implemented.`}
        />
      </SectionCard>

      {footer}
    </>
  );
}
