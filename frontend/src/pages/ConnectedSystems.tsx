/** Connected Systems: real connection state, health, sync, revoke. */

import { useState } from "react";
import { Link } from "react-router-dom";
import { api, type Connection } from "../api/client";
import {
  Banner,
  Badge,
  Empty,
  ErrorNote,
  HealthDot,
  Loading,
  Stat,
  StatusBadge,
  formatDate,
  relativeTime,
} from "../components/ui";
import { useApi, useAction } from "../lib/useApi";

export default function ConnectedSystems() {
  const connections = useApi(() => api.listConnections(), []);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ tone: "success" | "danger"; text: string } | null>(null);

  const rows = connections.data ?? [];
  const healthy = rows.filter((row) => row.health_status === "healthy").length;
  const failing = rows.filter((row) => row.status === "failed" || row.health_status === "unhealthy").length;

  const testAction = useAction((id: string) => api.testConnection(id));
  const syncAction = useAction((id: string) => api.runSync(id));
  const revokeAction = useAction((id: string) => api.revokeConnection(id));

  async function test(connection: Connection) {
    setNotice(null);
    const result = await testAction.run(connection.connection_id);
    if (result) {
      setNotice({
        tone: result.success ? "success" : "danger",
        text: `${connection.display_name}: ${result.message}`,
      });
    } else if (testAction.error) {
      setNotice({ tone: "danger", text: String((testAction.error as Error).message) });
    }
    connections.reload();
  }

  async function sync(connection: Connection) {
    setNotice(null);
    const result = await syncAction.run(connection.connection_id);
    if (result) {
      setNotice({
        tone: result.status === "succeeded" ? "success" : "danger",
        text: `${connection.display_name}: sync ${result.status} — ${result.records_written} records written${
          result.error ? ` (${result.error})` : ""
        }`,
      });
    } else if (syncAction.error) {
      setNotice({ tone: "danger", text: String((syncAction.error as Error).message) });
    }
    connections.reload();
  }

  async function revoke(connection: Connection) {
    if (!window.confirm(`Revoke ${connection.display_name}? Stored credentials are destroyed.`)) return;
    await revokeAction.run(connection.connection_id);
    connections.reload();
  }

  return (
    <>
      <div className="page-head">
        <h1 className="page-title">Connected Systems</h1>
        <p className="page-sub">
          Every application Humisense is authorised to read, its real health and the last
          synchronisation that actually ran.
        </p>
      </div>

      {connections.error && <ErrorNote error={connections.error} />}
      {notice && <Banner tone={notice.tone}>{notice.text}</Banner>}

      <div className="grid grid-4" style={{ marginBottom: 20 }}>
        <Stat value={rows.length} label="Connections" />
        <Stat value={healthy} label="Healthy" />
        <Stat value={failing} label="Failing" />
        <Stat
          value={rows.filter((row) => row.last_successful_sync).length}
          label="Ever synced"
        />
      </div>

      {connections.loading && <Loading rows={4} />}

      {!connections.loading && rows.length === 0 && (
        <Empty>
          No applications connected yet.{" "}
          <Link to="/marketplace">Browse the marketplace</Link> to connect your first system.
        </Empty>
      )}

      {rows.length > 0 && (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <table className="data">
            <thead>
              <tr>
                <th>Connection</th>
                <th>Status</th>
                <th>Health</th>
                <th>Last successful sync</th>
                <th>Scopes</th>
                <th style={{ textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((connection) => (
                <>
                  <tr key={connection.connection_id}>
                    <td>
                      <div style={{ fontWeight: 600 }}>{connection.display_name}</div>
                      <div className="dim" style={{ fontSize: 11.5 }}>
                        {connection.provider}
                        {connection.account_identifier ? ` · ${connection.account_identifier}` : ""}
                      </div>
                    </td>
                    <td>
                      <StatusBadge status={connection.status} />
                    </td>
                    <td>
                      <span className="row" style={{ gap: 6 }}>
                        <HealthDot status={connection.health_status} />
                        <span style={{ fontSize: 12 }}>{connection.health_status}</span>
                        {connection.health_latency_ms != null && (
                          <span className="dim" style={{ fontSize: 11 }}>
                            {Math.round(connection.health_latency_ms)}ms
                          </span>
                        )}
                      </span>
                    </td>
                    <td>
                      <div style={{ fontSize: 12 }}>{relativeTime(connection.last_successful_sync)}</div>
                      <div className="dim" style={{ fontSize: 11 }}>
                        {formatDate(connection.last_successful_sync)}
                      </div>
                    </td>
                    <td>
                      {connection.granted_scopes.length > 0 ? (
                        <span className="row wrap" style={{ gap: 4 }}>
                          {connection.granted_scopes.slice(0, 3).map((scope) => (
                            <span className="chip" key={scope}>
                              {scope}
                            </span>
                          ))}
                          {connection.granted_scopes.length > 3 && (
                            <span className="chip">+{connection.granted_scopes.length - 3}</span>
                          )}
                        </span>
                      ) : (
                        <span className="dim">not reported</span>
                      )}
                    </td>
                    <td>
                      <div className="row" style={{ justifyContent: "flex-end", gap: 6 }}>
                        <button
                          className="btn btn-sm"
                          disabled={testAction.loading}
                          onClick={() => test(connection)}
                        >
                          Test
                        </button>
                        <button
                          className="btn btn-sm"
                          disabled={syncAction.loading || connection.status === "revoked"}
                          onClick={() => sync(connection)}
                        >
                          Sync
                        </button>
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={() =>
                            setExpanded(expanded === connection.connection_id ? null : connection.connection_id)
                          }
                        >
                          {expanded === connection.connection_id ? "Hide" : "Details"}
                        </button>
                      </div>
                    </td>
                  </tr>
                  {expanded === connection.connection_id && (
                    <tr key={`${connection.connection_id}-detail`}>
                      <td colSpan={6} style={{ background: "var(--bg-panel)" }}>
                        <ConnectionDetail
                          connection={connection}
                          onRevoke={() => revoke(connection)}
                        />
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function ConnectionDetail({ connection, onRevoke }: { connection: Connection; onRevoke: () => void }) {
  const runs = useApi(() => api.listSyncRuns(connection.connection_id), [connection.connection_id]);

  return (
    <div className="grid grid-2" style={{ gap: 18, padding: "6px 0" }}>
      <div>
        <div className="section-title" style={{ marginTop: 0 }}>
          Connection
        </div>
        <dl className="kv">
          <dt>Connection ID</dt>
          <dd className="mono">{connection.connection_id}</dd>
          <dt>Created</dt>
          <dd>{formatDate(connection.created_at)}</dd>
          <dt>Credential ref</dt>
          <dd className="mono">{connection.credential_reference_id ?? "—"}</dd>
          <dt>Credential rotated</dt>
          <dd>{formatDate(connection.credential_rotated_at)}</dd>
          <dt>Last error</dt>
          <dd>{connection.last_error ?? "—"}</dd>
        </dl>
        {connection.last_error && <Banner tone="danger">{connection.last_error}</Banner>}
        <button className="btn btn-danger btn-sm" onClick={onRevoke} style={{ marginTop: 10 }}>
          Revoke connection
        </button>
      </div>
      <div>
        <div className="section-title" style={{ marginTop: 0 }}>
          Recent sync runs
        </div>
        {runs.loading && <Loading rows={2} />}
        {runs.data && runs.data.length === 0 && <Empty>No sync runs recorded yet.</Empty>}
        {runs.data && runs.data.length > 0 && (
          <table className="data">
            <thead>
              <tr>
                <th>Started</th>
                <th>Mode</th>
                <th>Status</th>
                <th>Records</th>
              </tr>
            </thead>
            <tbody>
              {runs.data.slice(0, 6).map((run) => (
                <tr key={run.run_id}>
                  <td>{formatDate(run.started_at)}</td>
                  <td>{run.mode}</td>
                  <td>
                    <Badge
                      tone={
                        run.status === "succeeded"
                          ? "success"
                          : run.status === "failed"
                            ? "danger"
                            : "info"
                      }
                    >
                      {run.status}
                    </Badge>
                  </td>
                  <td>
                    {run.records_written} written
                    {run.records_skipped > 0 ? ` · ${run.records_skipped} skipped` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
