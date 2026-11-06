/** Integration Health Centre: sync status, failures, dead letters, audit. */

import { useState } from "react";
import { api } from "../api/client";
import {
  Banner,
  Badge,
  Empty,
  ErrorNote,
  Loading,
  Stat,
  formatDate,
  relativeTime,
} from "../components/ui";
import { useApi } from "../lib/useApi";

type Tab = "connections" | "dead-letters" | "audit" | "contract";

export default function HealthCentre() {
  const [tab, setTab] = useState<Tab>("connections");

  const health = useApi(() => api.health(), []);
  const connections = useApi(() => api.listConnections(), []);
  const deadLetters = useApi(() => api.listDeadLetters(), []);
  const audit = useApi(() => api.listAuditLogs(), []);
  const contract = useApi(() => api.eventContract(), []);

  const rows = connections.data ?? [];
  const failing = rows.filter((row) => row.status === "failed" || row.health_status === "unhealthy");
  const degraded = rows.filter((row) => row.health_status === "degraded" || row.status === "degraded");

  return (
    <>
      <div className="page-head">
        <h1 className="page-title">Integration Health Centre</h1>
        <p className="page-sub">
          Synchronisation status, failures, dead-letter records and the full audit trail of
          integration administration.
        </p>
      </div>

      {health.error && <ErrorNote error={health.error} />}

      <div className="grid grid-4" style={{ marginBottom: 20 }}>
        <Stat value={rows.length} label="Connections" />
        <Stat value={failing.length} label="Failing" />
        <Stat value={degraded.length} label="Degraded" />
        <Stat value={deadLetters.data?.length ?? 0} label="Dead letters" />
      </div>

      {(failing.length > 0 || degraded.length > 0) && (
        <Banner tone={failing.length > 0 ? "danger" : "warning"}>
          {failing.length > 0
            ? `${failing.length} connection(s) failing: ${failing.map((row) => row.display_name).join(", ")}`
            : `${degraded.length} connection(s) degraded: ${degraded.map((row) => row.display_name).join(", ")}`}
        </Banner>
      )}

      <div className="toolbar" style={{ gap: 6 }}>
        {(
          [
            ["connections", "Sync status"],
            ["dead-letters", `Dead letters (${deadLetters.data?.length ?? 0})`],
            ["audit", "Audit records"],
            ["contract", "Layer 2 contract"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            className={`btn btn-sm${tab === value ? " btn-primary" : ""}`}
            onClick={() => setTab(value)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "connections" && (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          {connections.loading && <div style={{ padding: 16 }}><Loading rows={3} /></div>}
          {!connections.loading && rows.length === 0 && (
            <div style={{ padding: 16 }}><Empty>No connections to monitor.</Empty></div>
          )}
          {rows.length > 0 && (
            <table className="data">
              <thead>
                <tr>
                  <th>Connection</th>
                  <th>Status</th>
                  <th>Health</th>
                  <th>Last success</th>
                  <th>Last error</th>
                  <th>Failures</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.connection_id}>
                    <td style={{ fontWeight: 600 }}>{row.display_name}</td>
                    <td>
                      <Badge
                        tone={
                          row.status === "healthy" || row.status === "connected"
                            ? "success"
                            : row.status === "failed" || row.status === "revoked"
                              ? "danger"
                              : row.status === "degraded"
                                ? "warning"
                                : "info"
                        }
                      >
                        {row.status}
                      </Badge>
                    </td>
                    <td>{row.health_status}</td>
                    <td>{relativeTime(row.last_successful_sync)}</td>
                    <td className="muted truncate" style={{ maxWidth: 260 }}>
                      {row.last_error ?? "—"}
                    </td>
                    <td>{row.health_status === "unhealthy" ? "≥1" : "0"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab === "dead-letters" && (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          {deadLetters.loading && <div style={{ padding: 16 }}><Loading rows={3} /></div>}
          {deadLetters.data && deadLetters.data.length === 0 && (
            <div style={{ padding: 16 }}>
              <Empty>No dead-letter records. Records that fail repeatedly appear here.</Empty>
            </div>
          )}
          {deadLetters.data && deadLetters.data.length > 0 && (
            <table className="data">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Connection</th>
                  <th>Resource</th>
                  <th>Reason</th>
                  <th>Resolved</th>
                </tr>
              </thead>
              <tbody>
                {deadLetters.data.map((row) => (
                  <tr key={row.id}>
                    <td>{formatDate(row.created_at)}</td>
                    <td className="mono">{row.connection_id.slice(0, 8)}…</td>
                    <td>{row.resource_id ?? "—"}</td>
                    <td className="muted">{row.reason}</td>
                    <td>
                      <Badge tone={row.resolved ? "success" : "warning"}>
                        {row.resolved ? "resolved" : "open"}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab === "audit" && (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          {audit.loading && <div style={{ padding: 16 }}><Loading rows={4} /></div>}
          {audit.data && audit.data.length === 0 && (
            <div style={{ padding: 16 }}><Empty>No audit records yet.</Empty></div>
          )}
          {audit.data && audit.data.length > 0 && (
            <table className="data">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Action</th>
                  <th>Resource</th>
                  <th>Actor</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {audit.data.slice(0, 100).map((row) => (
                  <tr key={row.id}>
                    <td>{formatDate(row.created_at)}</td>
                    <td>
                      <Badge tone={row.action.includes("violation") ? "danger" : "neutral"}>
                        {row.action}
                      </Badge>
                    </td>
                    <td className="mono">
                      {row.resource_type}
                      {row.resource_id ? `/${row.resource_id.slice(0, 8)}…` : ""}
                    </td>
                    <td>{row.actor_id ?? "system"}</td>
                    <td className="mono truncate" style={{ maxWidth: 320 }}>
                      {JSON.stringify(row.detail)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab === "contract" && (
        <div className="card">
          {contract.loading && <Loading rows={3} />}
          {contract.error ? <ErrorNote error={contract.error} /> : null}
          {contract.data && (
            <>
              <div className="section-title" style={{ marginTop: 0 }}>
                Layer 2 event contract · v{contract.data.schema_version}
              </div>
              <dl className="kv">
                <dt>Delivery</dt>
                <dd>{String(contract.data.delivery.semantics)}</dd>
                <dt>Transport</dt>
                <dd>{String(contract.data.delivery.transport)}</dd>
                <dt>Ordering</dt>
                <dd>{String(contract.data.delivery.ordering)}</dd>
              </dl>
              <div className="section-title">Event types</div>
              <div className="stack">
                {(contract.data.event_types as Record<string, string>[]).map((item) => (
                  <div key={item.event_type} className="card" style={{ background: "var(--bg-panel)" }}>
                    <div className="mono" style={{ color: "var(--accent)" }}>
                      {String(item.event_type)}
                    </div>
                    <div className="muted" style={{ fontSize: 12.5 }}>
                      {String(item.description)}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </>
  );
}
