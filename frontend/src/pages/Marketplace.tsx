/** Integration Marketplace: browse, search and start a connection. */

import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type ConnectorDefinition } from "../api/client";
import {
  Banner,
  Badge,
  Empty,
  ErrorNote,
  Loading,
  StateBadge,
  categoryLabel,
  initials,
} from "../components/ui";
import { useApi } from "../lib/useApi";

export default function Marketplace() {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [installableOnly, setInstallableOnly] = useState(false);

  const catalogue = useApi(() => api.listConnectors(), []);
  const connections = useApi(() => api.listConnections(), []);
  const categories = useApi(() => api.listCategories(), []);

  const connectedByConnector = useMemo(() => {
    const map = new Map<string, number>();
    for (const connection of connections.data ?? []) {
      map.set(connection.connector_id, (map.get(connection.connector_id) ?? 0) + 1);
    }
    return map;
  }, [connections.data]);

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return (catalogue.data ?? []).filter((item) => {
      if (installableOnly && !item.is_installable) return false;
      if (category && item.category !== category) return false;
      if (!needle) return true;
      return (
        item.display_name.toLowerCase().includes(needle) ||
        item.provider.toLowerCase().includes(needle) ||
        item.description.toLowerCase().includes(needle)
      );
    });
  }, [catalogue.data, search, category, installableOnly]);

  const installableCount = (catalogue.data ?? []).filter((item) => item.is_installable).length;

  return (
    <>
      <div className="page-head">
        <h1 className="page-title">Integration Marketplace</h1>
        <p className="page-sub">
          {catalogue.data
            ? `${catalogue.data.length} integration targets catalogued, ${installableCount} ready to connect.`
            : "Loading the connector catalogue…"}{" "}
          A connector is only shown as connectable when a working implementation exists. Planned
          integrations are labelled honestly.
        </p>
      </div>

      {catalogue.error && <ErrorNote error={catalogue.error} />}

      <div className="toolbar">
        <input
          className="input"
          placeholder="Search applications, vendors…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <select className="select" value={category} onChange={(event) => setCategory(event.target.value)}>
          <option value="">All categories</option>
          {(categories.data ?? []).map((value) => (
            <option key={value} value={value}>
              {categoryLabel(value)}
            </option>
          ))}
        </select>
        <label className="checkbox-row" style={{ padding: "6px 11px" }}>
          <input
            type="checkbox"
            checked={installableOnly}
            onChange={(event) => setInstallableOnly(event.target.checked)}
          />
          Ready to connect only
        </label>
        <span className="grow" />
        <span className="dim" style={{ fontSize: 12 }}>
          {filtered.length} shown
        </span>
      </div>

      {catalogue.loading && <Loading rows={6} />}

      {!catalogue.loading && filtered.length === 0 && (
        <Empty>No connectors match the current filters.</Empty>
      )}

      <div className="grid grid-3">
        {filtered.map((item) => (
          <ConnectorCard
            key={item.connector_id}
            item={item}
            connectedCount={connectedByConnector.get(item.connector_id) ?? 0}
          />
        ))}
      </div>
    </>
  );
}

function ConnectorCard({ item, connectedCount }: { item: ConnectorDefinition; connectedCount: number }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className={`connector-card${item.is_installable ? "" : " is-pending"}`}>
      <div className="row" style={{ alignItems: "flex-start" }}>
        <div className="connector-icon">{initials(item.display_name)}</div>
        <div className="grow">
          <div className="row-between">
            <strong style={{ fontSize: 13.5 }}>{item.display_name}</strong>
            {connectedCount > 0 && <Badge tone="success">{connectedCount} connected</Badge>}
          </div>
          <div className="dim" style={{ fontSize: 11.5 }}>
            {item.provider} · {categoryLabel(item.category)}
          </div>
        </div>
      </div>

      <p className="muted" style={{ margin: 0, fontSize: 12.5 }}>
        {item.description}
      </p>

      <div className="row wrap" style={{ gap: 5 }}>
        <StateBadge state={item.implementation_state} />
        {item.is_read_only && <span className="chip">read-only</span>}
        {item.supports_webhooks && <span className="chip">webhooks</span>}
        {item.supports_incremental && <span className="chip">incremental</span>}
        {item.requires_on_premise && <span className="chip">on-premise</span>}
      </div>

      {!item.is_installable && (
        <Banner tone="warning">
          Not yet installable. This is a catalogued integration target, not a working connector.
        </Banner>
      )}

      {expanded && (
        <dl className="kv" style={{ marginTop: 4 }}>
          <dt>Auth</dt>
          <dd>{item.auth_types.map((value) => value.replace(/_/g, " ")).join(", ") || "—"}</dd>
          <dt>Resources</dt>
          <dd>{item.supported_resources.join(", ") || "—"}</dd>
          <dt>Required scopes</dt>
          <dd>{item.required_scopes.join(", ") || "—"}</dd>
          {item.required_license && (
            <>
              <dt>Licence</dt>
              <dd>{item.required_license}</dd>
            </>
          )}
          {item.known_limitations.length > 0 && (
            <>
              <dt>Limitations</dt>
              <dd>
                <ul style={{ margin: 0, paddingLeft: 16 }}>
                  {item.known_limitations.map((value) => (
                    <li key={value}>{value}</li>
                  ))}
                </ul>
              </dd>
            </>
          )}
        </dl>
      )}

      <div className="row" style={{ marginTop: "auto", paddingTop: 4 }}>
        <button className="btn btn-ghost btn-sm" onClick={() => setExpanded((value) => !value)}>
          {expanded ? "Hide details" : "Details"}
        </button>
        <span className="grow" />
        {item.is_installable ? (
          <Link className="btn btn-primary btn-sm" to={`/connections/new/${item.connector_id}`}>
            Connect
          </Link>
        ) : (
          <button className="btn btn-sm" disabled title="No working implementation yet">
            Unavailable
          </button>
        )}
      </div>
    </div>
  );
}
