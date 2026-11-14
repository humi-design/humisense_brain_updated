/**
 * Apps — the hub for connected applications.
 *
 * This is a real, working page: the counts and the connector health summary are
 * read from the Layer 1 API. The individual integration screens (marketplace,
 * connected systems, discovery, studio, health) are the existing, working Layer
 * 1 surfaces, mounted under /apps.
 *
 * If the API cannot be reached the page says so rather than showing zeros,
 * because "0 connected" and "we could not ask" mean very different things to
 * someone checking whether their integrations are alive.
 */

import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { useApi } from "../../lib/useApi";
import { PageHeader } from "../../components/layout/PageHeader";
import { SectionCard } from "../../components/layout/SectionCard";
import { ErrorState, LoadingState } from "../../components/feedback/States";
import { Badge } from "../../components/ui";
import {
  AppWindow,
  Compass,
  Gauge,
  LayoutGrid,
  Link2,
  SlidersHorizontal,
  type LucideIcon,
} from "../../components/ui/icons";

interface Destination {
  to: string;
  title: string;
  description: string;
  icon: LucideIcon;
}

const DESTINATIONS: Destination[] = [
  {
    to: "/apps/marketplace",
    title: "Integration Marketplace",
    description:
      "Browse the connector catalogue and start a new connection.",
    icon: AppWindow,
  },
  {
    to: "/apps/connections",
    title: "Connected Systems",
    description:
      "Every connected application, its health and its permissions.",
    icon: Link2,
  },
  {
    to: "/apps/discovery",
    title: "Technology Discovery",
    description:
      "Assess what software the organization uses and how it can be integrated.",
    icon: Compass,
  },
  {
    to: "/apps/studio",
    title: "Universal Connector Studio",
    description:
      "Configure REST, GraphQL, SQL, file and webhook connectors.",
    icon: SlidersHorizontal,
  },
  {
    to: "/apps/health",
    title: "Integration Health Centre",
    description: "Synchronization status, errors, retries and audit records.",
    icon: Gauge,
  },
];

export default function Apps() {
  const health = useApi(() => api.health(), []);
  const connections = useApi(() => api.listConnections(), []);

  const connectionList = connections.data ?? [];
  const healthy = connectionList.filter((c) => c.status === "healthy").length;
  const needingAttention = connectionList.filter((c) =>
    ["degraded", "failed", "revoked"].includes(c.status),
  ).length;

  return (
    <>
      <PageHeader
        title="Apps"
        description="The applications Humisense is connected to, and the tools for connecting more."
        actions={
          <Link to="/apps/marketplace" className="hs-btn hs-btn-primary hs-btn-sm">
            <AppWindow size={14} aria-hidden="true" />
            <span>Browse integrations</span>
          </Link>
        }
      />

      <SectionCard
        title="Integration status"
        icon={LayoutGrid}
        description="Live figures from the connector platform."
      >
        {health.loading || connections.loading ? (
          <LoadingState rows={2} compact />
        ) : health.error || connections.error ? (
          <ErrorState
            compact
            title="Could not read integration status"
            description={
              (health.error ?? connections.error) instanceof Error
                ? ((health.error ?? connections.error) as Error).message
                : "The connector platform did not respond."
            }
            action={{ label: "Retry", onClick: () => {
              health.reload();
              connections.reload();
            } }}
          />
        ) : (
          <div className="hs-stat-row">
            <div className="hs-stat">
              <span className="hs-stat-value">{connectionList.length}</span>
              <span className="hs-stat-label">Connected systems</span>
            </div>
            <div className="hs-stat">
              <span className="hs-stat-value">{healthy}</span>
              <span className="hs-stat-label">Healthy</span>
            </div>
            <div className="hs-stat">
              <span className="hs-stat-value">{needingAttention}</span>
              <span className="hs-stat-label">Needing attention</span>
            </div>
            <div className="hs-stat">
              <span className="hs-stat-value">
                {health.data?.connectors_installable ?? "—"}
              </span>
              <span className="hs-stat-label">Connectors ready</span>
            </div>
            <div className="hs-stat">
              <span className="hs-stat-value">
                {health.data?.connectors_registered ?? "—"}
              </span>
              <span className="hs-stat-label">In catalogue</span>
            </div>
          </div>
        )}
      </SectionCard>

      <SectionCard title="Integration tools" icon={SlidersHorizontal}>
        <div className="hs-destination-grid">
          {DESTINATIONS.map((destination) => {
            const Icon = destination.icon;
            return (
              <Link
                key={destination.to}
                to={destination.to}
                className="hs-destination"
              >
                <span className="hs-destination-icon" aria-hidden="true">
                  <Icon size={17} />
                </span>
                <span className="hs-destination-body">
                  <span className="hs-destination-title">
                    {destination.title}
                  </span>
                  <span className="hs-destination-desc">
                    {destination.description}
                  </span>
                </span>
              </Link>
            );
          })}
        </div>
      </SectionCard>

      <SectionCard
        title="Planned integrations"
        icon={AppWindow}
        description="Where the product is going next."
      >
        <div className="hs-row wrap" style={{ gap: 8 }}>
          <Badge tone="neutral">Email and calendars</Badge>
          <Badge tone="neutral">Meetings and transcripts</Badge>
          <Badge tone="neutral">CRM and ERP records</Badge>
          <Badge tone="neutral">Industrial historians</Badge>
          <Badge tone="neutral">Document stores</Badge>
        </div>
        <p className="hs-muted" style={{ marginTop: 10, fontSize: 12.5 }}>
          The catalogue already lists these as integration targets. They become
          connectable as each connector is implemented and verified — the
          marketplace only shows a connector as connectable once it actually
          works.
        </p>
      </SectionCard>
    </>
  );
}
