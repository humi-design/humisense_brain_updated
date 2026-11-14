/**
 * Today — the unified attention workspace.
 *
 * This milestone builds the *structure*, not the work intelligence. The
 * sections below are the real information architecture; the data that will
 * fill them comes from the Work Intelligence layer, which does not exist yet.
 *
 * That constraint is honoured rather than papered over: every section renders
 * a labelled "awaiting the Work Intelligence layer" state. Nothing here is
 * fabricated, and no placeholder can be mistaken for a customer's real work.
 */

import { useAuth } from "../../auth/AuthProvider";
import { PageHeader } from "../../components/layout/PageHeader";
import { SectionCard } from "../../components/layout/SectionCard";
import { NotAvailableState } from "../../components/feedback/States";
import {
  CheckCircle2,
  Clock,
  Inbox,
  ListChecks,
  ShieldCheck,
  Sparkles,
  UserCheck,
} from "../../components/ui/icons";

/**
 * One section of the attention workspace.
 *
 * `sources` names the systems that will feed the section, so the empty state is
 * informative rather than blank.
 */
const SECTIONS = [
  {
    id: "attention",
    title: "Needs your attention",
    icon: Inbox,
    description:
      "Items the Brain has judged to require a decision from you specifically.",
    sources: "Missions, approvals and connected applications",
  },
  {
    id: "today",
    title: "Today's work",
    icon: ListChecks,
    description: "Commitments, deadlines and scheduled work for today.",
    sources: "Tasks and calendar",
  },
  {
    id: "approvals",
    title: "Awaiting your approval",
    icon: ShieldCheck,
    description:
      "Prepared work stopped at a decision point for your authorization.",
    sources: "Governance and agent execution",
  },
  {
    id: "ai",
    title: "Handled by AI",
    icon: Sparkles,
    description:
      "Work completed by your AI workforce, with its outcome and evidence.",
    sources: "Workforce execution and verification",
  },
  {
    id: "human",
    title: "Yours to do",
    icon: UserCheck,
    description: "Work the Brain has prepared for a person to complete.",
    sources: "Prepared work items",
  },
  {
    id: "completed",
    title: "Recently completed",
    icon: CheckCircle2,
    description: "Work finished recently, by you or by an agent.",
    sources: "Completed work and outcomes",
  },
] as const;

export default function Today() {
  const { identity, memberships, selectedTenantId } = useAuth();

  const active =
    memberships.find((m) => m.tenant_id === selectedTenantId) ??
    memberships[0] ??
    null;

  return (
    <>
      <PageHeader
        title="Today"
        description={
          active
            ? `Your attention workspace for ${active.tenant_name}.`
            : "Your unified attention workspace."
        }
        meta={
          identity && (
            <span className="hs-header-meta">
              <Clock size={13} aria-hidden="true" />
              {new Date().toLocaleDateString(undefined, {
                weekday: "long",
                day: "numeric",
                month: "long",
              })}
            </span>
          )
        }
      />

      <div className="hs-notice" role="note">
        <Sparkles size={15} aria-hidden="true" />
        <div>
          <strong>The workspace is ready. The intelligence is not connected yet.</strong>
          <p>
            The sections below are the real structure of Today. They fill once
            the Work Intelligence layer publishes work items, approvals and
            agent outcomes. Nothing here is simulated.
          </p>
        </div>
      </div>

      <div className="hs-section-grid">
        {SECTIONS.map((section) => {
          const Icon = section.icon;
          return (
            <SectionCard
              key={section.id}
              id={section.id}
              title={section.title}
              icon={Icon}
              description={section.description}
              count={0}
            >
              <NotAvailableState
                compact
                title="Awaiting the Work Intelligence layer"
                description={
                  <>
                    Will draw from: {section.sources}.
                  </>
                }
              />
            </SectionCard>
          );
        })}
      </div>
    </>
  );
}
