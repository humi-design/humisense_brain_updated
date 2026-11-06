/**
 * Connection Wizard: provider -> authentication -> test -> resources -> sync -> complete.
 *
 * Every step reflects real backend state. The wizard never claims a connection
 * works before the backend has confirmed it, and the "test" step shows the
 * actual provider response.
 */

import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  api,
  type Connection,
  type ConnectionResource,
  type TestConnectionResult,
} from "../api/client";
import {
  Banner,
  Badge,
  ErrorNote,
  Loading,
  StateBadge,
  categoryLabel,
} from "../components/ui";
import { useApi } from "../lib/useApi";

const STEPS = ["Provider", "Authentication", "Test connection", "Resources", "Synchronisation", "Complete"];

const CREDENTIAL_FIELDS: Record<string, { key: string; label: string; placeholder: string; secret: boolean }[]> = {
  github: [{ key: "token", label: "Personal access token", placeholder: "ghp_…", secret: true }],
  slack: [{ key: "token", label: "Bot token", placeholder: "xoxb-…", secret: true }],
  canary_labs: [
    { key: "api_key", label: "API key", placeholder: "Canary Web API key", secret: true },
    { key: "username", label: "Username (optional)", placeholder: "if using basic auth", secret: false },
    { key: "password", label: "Password (optional)", placeholder: "if using basic auth", secret: true },
  ],
  universal_webhook: [
    { key: "webhook_secret", label: "Webhook signing secret", placeholder: "shared secret", secret: true },
  ],
  universal_rest: [{ key: "token", label: "Bearer / API token", placeholder: "token", secret: true }],
  universal_graphql: [{ key: "token", label: "Bearer / API token", placeholder: "token", secret: true }],
  universal_sql: [
    { key: "username", label: "Database username", placeholder: "readonly_user", secret: false },
    { key: "password", label: "Database password", placeholder: "••••••", secret: true },
  ],
  universal_file: [],
};

export default function ConnectionWizard() {
  const { connectorId = "" } = useParams();
  const navigate = useNavigate();

  const definition = useApi(() => api.getConnector(connectorId), [connectorId]);

  const [step, setStep] = useState(0);
  const [displayName, setDisplayName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [host, setHost] = useState("");
  const [port, setPort] = useState("");
  const [database, setDatabase] = useState("");
  const [allowPrivate, setAllowPrivate] = useState(false);
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const [adapterJson, setAdapterJson] = useState("{}");

  const [connection, setConnection] = useState<Connection | null>(null);
  const [testResult, setTestResult] = useState<TestConnectionResult | null>(null);
  const [resources, setResources] = useState<ConnectionResource[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [syncMode, setSyncMode] = useState("incremental");
  const [pageSize, setPageSize] = useState(100);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const credentialFields = CREDENTIAL_FIELDS[connectorId] ?? [
    { key: "token", label: "API token", placeholder: "token", secret: true },
  ];

  const isAdapter = connectorId.startsWith("universal_");
  const isSql = connectorId === "universal_sql";
  const isFile = connectorId === "universal_file";

  const configuration = useMemo(() => {
    const options: Record<string, unknown> = {};
    if (allowPrivate) options.allow_private = true;
    if (isAdapter && !isFile) {
      try {
        options.adapter = JSON.parse(adapterJson);
      } catch {
        options.adapter = undefined;
      }
    }
    if (isFile) {
      try {
        options.adapter = JSON.parse(adapterJson);
      } catch {
        options.adapter = undefined;
      }
    }
    return {
      base_url: baseUrl || null,
      host: host || null,
      port: port ? Number(port) : null,
      database: database || null,
      options,
    };
  }, [baseUrl, host, port, database, allowPrivate, adapterJson, isAdapter, isFile]);

  async function createAndTest() {
    setBusy(true);
    setError(null);
    try {
      const created = await api.createConnection({
        connector_id: connectorId,
        display_name: displayName || `${definition.data?.display_name ?? connectorId}`,
        configuration,
        credentials,
      });
      setConnection(created);
      const result = await api.testConnection(created.connection_id);
      setTestResult(result);
      setStep(2);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function retest() {
    if (!connection) return;
    setBusy(true);
    setError(null);
    try {
      setTestResult(await api.testConnection(connection.connection_id));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function loadResources() {
    if (!connection) return;
    setBusy(true);
    setError(null);
    try {
      const found = await api.discoverResources(connection.connection_id);
      setResources(found);
      setStep(3);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function saveResources() {
    if (!connection) return;
    setBusy(true);
    setError(null);
    try {
      await api.selectResources(connection.connection_id, selected);
      setStep(4);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function saveSync() {
    if (!connection) return;
    setBusy(true);
    setError(null);
    try {
      await api.configureSync(connection.connection_id, { mode: syncMode, page_size: pageSize });
      setStep(5);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  if (definition.loading) return <Loading rows={5} />;
  if (definition.error) return <ErrorNote error={definition.error} />;
  const connector = definition.data!;

  return (
    <>
      <div className="page-head">
        <Link to="/marketplace" className="dim" style={{ fontSize: 12 }}>
          ← Back to marketplace
        </Link>
        <h1 className="page-title" style={{ marginTop: 8 }}>
          Connect {connector.display_name}
        </h1>
        <p className="page-sub">
          {connector.description}{" "}
          <StateBadge state={connector.implementation_state} />
        </p>
      </div>

      <div className="wizard-steps">
        {STEPS.map((label, index) => (
          <div
            key={label}
            className={`wizard-step${index === step ? " active" : ""}${index < step ? " done" : ""}`}
          >
            <span className="wizard-step-num">{index < step ? "✓" : index + 1}</span>
            {label}
          </div>
        ))}
      </div>

      {error && <ErrorNote error={error} />}

      {step === 0 && (
        <div className="card">
          <div className="section-title">Provider and identity</div>
          <div className="field">
            <label className="label">Connection name</label>
            <input
              className="input"
              placeholder={`e.g. ${connector.display_name} — Production`}
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
            />
            <div className="hint">A label your team will recognise in Connected Systems.</div>
          </div>
          <dl className="kv">
            <dt>Provider</dt>
            <dd>{connector.provider}</dd>
            <dt>Category</dt>
            <dd>{categoryLabel(connector.category)}</dd>
            <dt>Authentication</dt>
            <dd>{connector.auth_types.map((value) => value.replace(/_/g, " ")).join(", ")}</dd>
            <dt>Access</dt>
            <dd>{connector.is_read_only ? "Read-only" : "Read and write"}</dd>
            {connector.required_license && (
              <>
                <dt>Licence required</dt>
                <dd>{connector.required_license}</dd>
              </>
            )}
          </dl>
          {connector.known_limitations.length > 0 && (
            <Banner tone="warning">
              <div>
                <strong>Known limitations</strong>
                <ul style={{ margin: "6px 0 0", paddingLeft: 16 }}>
                  {connector.known_limitations.map((value) => (
                    <li key={value}>{value}</li>
                  ))}
                </ul>
              </div>
            </Banner>
          )}
          <div className="row" style={{ marginTop: 16 }}>
            <span className="grow" />
            <button className="btn btn-primary" onClick={() => setStep(1)}>
              Continue
            </button>
          </div>
        </div>
      )}

      {step === 1 && (
        <div className="card">
          <div className="section-title">Authentication and endpoint</div>

          {(isAdapter || connectorId === "canary_labs") && (
            <>
              <div className="field">
                <label className="label">Base URL</label>
                <input
                  className="input"
                  placeholder="https://api.example.com/v1"
                  value={baseUrl}
                  onChange={(event) => setBaseUrl(event.target.value)}
                />
                <div className="hint">
                  Must be reachable and permitted by the egress policy. Private addresses require
                  an explicit opt-in.
                </div>
              </div>
              {isSql && (
                <div className="grid grid-2">
                  <div className="field">
                    <label className="label">Host</label>
                    <input className="input" value={host} onChange={(event) => setHost(event.target.value)} />
                  </div>
                  <div className="field">
                    <label className="label">Port</label>
                    <input className="input" value={port} onChange={(event) => setPort(event.target.value)} />
                  </div>
                </div>
              )}
              {isSql && (
                <div className="field">
                  <label className="label">Database name / path</label>
                  <input
                    className="input"
                    value={database}
                    onChange={(event) => setDatabase(event.target.value)}
                  />
                </div>
              )}
            </>
          )}

          {credentialFields.map((field) => (
            <div className="field" key={field.key}>
              <label className="label">{field.label}</label>
              <input
                className="input"
                type={field.secret ? "password" : "text"}
                placeholder={field.placeholder}
                value={credentials[field.key] ?? ""}
                onChange={(event) =>
                  setCredentials((current) => ({ ...current, [field.key]: event.target.value }))
                }
                autoComplete="off"
              />
            </div>
          ))}

          {isAdapter && (
            <div className="field">
              <label className="label">Adapter definition (JSON)</label>
              <textarea
                className="textarea"
                value={adapterJson}
                onChange={(event) => setAdapterJson(event.target.value)}
                spellCheck={false}
              />
              <div className="hint">
                Declarative schema only — no code is executed. For REST:{" "}
                <span className="mono">{`{"base_url": "...", "resources": [{"id": "items", "path": "/items"}]}`}</span>
              </div>
            </div>
          )}

          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={allowPrivate}
              onChange={(event) => setAllowPrivate(event.target.checked)}
            />
            Allow private / on-premise network targets for this connection
          </label>

          <Banner tone="info">
            Credentials are encrypted with AES-256-GCM and bound to this tenant and connection. They
            are never returned by the API or written to logs.
          </Banner>

          <div className="row" style={{ marginTop: 16 }}>
            <button className="btn btn-ghost" onClick={() => setStep(0)}>
              Back
            </button>
            <span className="grow" />
            <button className="btn btn-primary" disabled={busy} onClick={createAndTest}>
              {busy ? <span className="spinner" /> : null}
              {busy ? "Testing…" : "Create and test connection"}
            </button>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="card">
          <div className="section-title">Test connection</div>
          {testResult ? (
            <>
              <Banner tone={testResult.success ? "success" : "danger"}>
                <div>
                  <strong>{testResult.success ? "Connection verified" : "Connection failed"}</strong>
                  <div style={{ marginTop: 4 }}>{testResult.message}</div>
                </div>
              </Banner>
              <dl className="kv">
                <dt>Latency</dt>
                <dd>{testResult.latency_ms ? `${Math.round(testResult.latency_ms)} ms` : "—"}</dd>
                <dt>Account</dt>
                <dd>{testResult.account_identifier ?? "—"}</dd>
                <dt>Granted scopes</dt>
                <dd>{testResult.granted_scopes.join(", ") || "not reported"}</dd>
              </dl>
            </>
          ) : (
            <Loading rows={2} />
          )}
          <div className="row" style={{ marginTop: 16 }}>
            <button className="btn" disabled={busy} onClick={retest}>
              Test again
            </button>
            <span className="grow" />
            <button
              className="btn btn-primary"
              disabled={busy || !testResult?.success}
              onClick={loadResources}
              title={testResult?.success ? undefined : "A successful test is required first"}
            >
              Continue to resources
            </button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="card">
          <div className="section-title">
            Authorised resources <Badge tone="neutral">{resources.length} found</Badge>
          </div>
          <p className="muted" style={{ fontSize: 12.5, marginTop: 0 }}>
            Only resources the granted scopes authorise are listed. Select the ones Humisense may
            read.
          </p>
          {resources.length === 0 ? (
            <Banner tone="warning">
              The provider returned no resources. Check the granted scopes, then re-test the
              connection.
            </Banner>
          ) : (
            <div className="stack" style={{ maxHeight: 380, overflowY: "auto" }}>
              {resources.map((resource) => (
                <label className="checkbox-row" key={resource.external_id}>
                  <input
                    type="checkbox"
                    checked={selected.includes(resource.external_id)}
                    onChange={(event) =>
                      setSelected((current) =>
                        event.target.checked
                          ? [...current, resource.external_id]
                          : current.filter((value) => value !== resource.external_id),
                      )
                    }
                  />
                  <span className="grow truncate">{resource.name}</span>
                  <span className="chip">{resource.resource_type}</span>
                  {resource.read_only && <span className="chip">read-only</span>}
                </label>
              ))}
            </div>
          )}
          <div className="row" style={{ marginTop: 16 }}>
            <button className="btn btn-ghost" onClick={() => setStep(2)}>
              Back
            </button>
            <span className="muted" style={{ fontSize: 12 }}>
              {selected.length} selected
            </span>
            <span className="grow" />
            <button className="btn btn-primary" disabled={busy || selected.length === 0} onClick={saveResources}>
              Continue
            </button>
          </div>
        </div>
      )}

      {step === 4 && (
        <div className="card">
          <div className="section-title">Synchronisation</div>
          <div className="grid grid-2">
            <div className="field">
              <label className="label">Mode</label>
              <select className="select" value={syncMode} onChange={(event) => setSyncMode(event.target.value)}>
                <option value="incremental">Incremental (changed records only)</option>
                <option value="full">Full (every record each run)</option>
                <option value="webhook">Webhook-triggered</option>
              </select>
            </div>
            <div className="field">
              <label className="label">Page size</label>
              <input
                className="input"
                type="number"
                min={1}
                max={10000}
                value={pageSize}
                onChange={(event) => setPageSize(Number(event.target.value))}
              />
            </div>
          </div>
          {!connector.supports_incremental && syncMode === "incremental" && (
            <Banner tone="warning">
              This connector does not advertise incremental sync; the run will behave as a full sync.
            </Banner>
          )}
          <Banner tone="info">
            Layer 1 retrieves and normalises records and publishes them to Layer 2. It does not
            interpret, prioritise or act on the data.
          </Banner>
          <div className="row" style={{ marginTop: 16 }}>
            <button className="btn btn-ghost" onClick={() => setStep(3)}>
              Back
            </button>
            <span className="grow" />
            <button className="btn btn-primary" disabled={busy} onClick={saveSync}>
              Finish setup
            </button>
          </div>
        </div>
      )}

      {step === 5 && connection && (
        <div className="card">
          <div className="section-title">Connection complete</div>
          <Banner tone="success">
            <div>
              <strong>{connection.display_name}</strong> is configured and authenticated. Run the
              first synchronisation from Connected Systems, or immediately here.
            </div>
          </Banner>
          <dl className="kv">
            <dt>Connection ID</dt>
            <dd className="mono">{connection.connection_id}</dd>
            <dt>Status</dt>
            <dd>
              <Badge tone="accent">{connection.status}</Badge>
            </dd>
            <dt>Resources selected</dt>
            <dd>{selected.length}</dd>
            <dt>Sync mode</dt>
            <dd>{syncMode}</dd>
          </dl>
          <div className="row" style={{ marginTop: 16 }}>
            <button
              className="btn btn-primary"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await api.runSync(connection.connection_id, undefined, syncMode);
                } catch (err) {
                  setError(err);
                } finally {
                  setBusy(false);
                  navigate("/connections");
                }
              }}
            >
              Run first synchronisation
            </button>
            <button className="btn" onClick={() => navigate("/connections")}>
              Go to Connected Systems
            </button>
          </div>
        </div>
      )}
    </>
  );
}
