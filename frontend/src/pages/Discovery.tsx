/** Company Technology Discovery: inventory import and integration assessment. */

import { useRef, useState } from "react";
import { api, type Assessment } from "../api/client";
import {
  Banner,
  Badge,
  Empty,
  ErrorNote,
  Loading,
  Stat,
  StateBadge,
  categoryLabel,
  formatDate,
} from "../components/ui";
import { useApi, useAction } from "../lib/useApi";

const CLASS_TONE: Record<string, "success" | "info" | "warning" | "danger" | "neutral" | "accent"> = {
  PREBUILT_CONNECTOR_AVAILABLE: "success",
  UNIVERSAL_ADAPTER_AVAILABLE: "info",
  CUSTOM_CONNECTOR_REQUIRED: "accent",
  VENDOR_ASSISTANCE_REQUIRED: "warning",
  MANUAL_IMPORT_AVAILABLE: "neutral",
  INTEGRATION_NOT_FEASIBLE: "danger",
  DISCOVERY_PENDING: "neutral",
};

export default function Discovery() {
  const assessments = useApi(() => api.listAssessments(), []);
  const [notice, setNotice] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const importAction = useAction((file: File) => api.importInventory(file));
  const assessAction = useAction((payload: Record<string, unknown>) => api.createAssessment(payload));

  const [form, setForm] = useState({
    application_name: "",
    vendor: "",
    openapi_available: false,
    has_api_docs: false,
    database_reachable: false,
    on_premise_only: false,
  });

  const rows = assessments.data ?? [];

  async function handleImport(file: File) {
    setNotice(null);
    const result = await importAction.run(file);
    if (result) setNotice(`Imported ${result.length} application(s) from ${file.name}.`);
    assessments.reload();
  }

  async function handleAssess() {
    setNotice(null);
    if (!form.application_name.trim()) {
      setNotice("Enter an application name first.");
      return;
    }
    const result = await assessAction.run(form);
    if (result) setNotice(`Assessed ${result.application_name}: ${result.integration_class}.`);
    setForm({ ...form, application_name: "", vendor: "" });
    assessments.reload();
  }

  return (
    <>
      <div className="page-head">
        <h1 className="page-title">Company Technology Discovery</h1>
        <p className="page-sub">
          Identify which applications your organisation uses and how each one can be integrated.
          Discovery uses only authorised sources — inventories you provide, API documentation and
          approved catalogues. It performs no network scanning and grants no data access.
        </p>
      </div>

      {assessments.error && <ErrorNote error={assessments.error} />}
      {importAction.error && <ErrorNote error={importAction.error} />}
      {assessAction.error && <ErrorNote error={assessAction.error} />}
      {notice && <Banner tone="success">{notice}</Banner>}

      <Banner tone="info">
        Discovery is not authorisation. Assessing an application records feasibility only; a
        separate, explicit connection is always required before any data is read.
      </Banner>

      <div className="grid grid-4" style={{ marginBottom: 20 }}>
        <Stat value={rows.length} label="Assessed" />
        <Stat
          value={rows.filter((row) => row.integration_class === "PREBUILT_CONNECTOR_AVAILABLE").length}
          label="Prebuilt route"
        />
        <Stat
          value={rows.filter((row) => row.integration_class === "UNIVERSAL_ADAPTER_AVAILABLE").length}
          label="Adapter route"
        />
        <Stat
          value={rows.filter((row) => row.integration_class.includes("CUSTOM") || row.integration_class.includes("VENDOR")).length}
          label="Needs build"
        />
      </div>

      <div className="grid grid-2">
        <div className="card">
          <div className="section-title" style={{ marginTop: 0 }}>
            Import an application inventory
          </div>
          <p className="muted" style={{ fontSize: 12.5, marginTop: 0 }}>
            CSV, TSV, JSON or XLSX with columns such as <span className="mono">name</span>,{" "}
            <span className="mono">vendor</span>, <span className="mono">category</span>.
          </p>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.tsv,.json,.xlsx,.xls"
            style={{ display: "none" }}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) handleImport(file);
              event.target.value = "";
            }}
          />
          <button
            className="btn btn-primary"
            disabled={importAction.loading}
            onClick={() => fileRef.current?.click()}
          >
            {importAction.loading ? <span className="spinner" /> : null}
            Choose inventory file
          </button>
        </div>

        <div className="card">
          <div className="section-title" style={{ marginTop: 0 }}>
            Assess a single application
          </div>
          <div className="field">
            <label className="label">Application name</label>
            <input
              className="input"
              value={form.application_name}
              onChange={(event) => setForm({ ...form, application_name: event.target.value })}
              placeholder="e.g. Acme Proprietary MES"
            />
          </div>
          <div className="field">
            <label className="label">Vendor (optional)</label>
            <input
              className="input"
              value={form.vendor}
              onChange={(event) => setForm({ ...form, vendor: event.target.value })}
              placeholder="e.g. Acme Corp"
            />
          </div>
          <div className="stack" style={{ gap: 6 }}>
            {(
              [
                ["openapi_available", "OpenAPI / Swagger specification available"],
                ["has_api_docs", "API documentation available"],
                ["database_reachable", "Database is reachable (read-only)"],
                ["on_premise_only", "On-premise only"],
              ] as const
            ).map(([key, label]) => (
              <label className="checkbox-row" key={key}>
                <input
                  type="checkbox"
                  checked={form[key]}
                  onChange={(event) => setForm({ ...form, [key]: event.target.checked })}
                />
                {label}
              </label>
            ))}
          </div>
          <div className="row" style={{ marginTop: 14 }}>
            <span className="grow" />
            <button className="btn btn-primary" disabled={assessAction.loading} onClick={handleAssess}>
              Assess
            </button>
          </div>
        </div>
      </div>

      <div className="section-title">Assessment results</div>
      {assessments.loading && <Loading rows={4} />}
      {!assessments.loading && rows.length === 0 && (
        <Empty>No applications assessed yet. Import an inventory or assess one manually.</Empty>
      )}

      {rows.length > 0 && (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <table className="data">
            <thead>
              <tr>
                <th>Application</th>
                <th>Category</th>
                <th>Integration class</th>
                <th>Method</th>
                <th>Read / Write</th>
                <th>Estimate</th>
                <th>Status</th>
                <th>Discovered</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <AssessmentRow key={row.assessment_id} row={row} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function AssessmentRow({ row }: { row: Assessment }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <tr onClick={() => setOpen((value) => !value)} style={{ cursor: "pointer" }}>
        <td>
          <div style={{ fontWeight: 600 }}>{row.application_name}</div>
          <div className="dim" style={{ fontSize: 11.5 }}>{row.vendor ?? "unknown vendor"}</div>
        </td>
        <td>{categoryLabel(row.category)}</td>
        <td>
          <Badge tone={CLASS_TONE[row.integration_class] ?? "neutral"}>
            {row.integration_class.replace(/_/g, " ").toLowerCase()}
          </Badge>
        </td>
        <td className="mono">{row.available_integration_method ?? "—"}</td>
        <td>
          <span className="row" style={{ gap: 4 }}>
            <Badge tone={row.read_capability ? "success" : "neutral"}>read</Badge>
            <Badge tone={row.write_capability ? "warning" : "neutral"}>write</Badge>
          </span>
        </td>
        <td>{row.implementation_estimate_days != null ? `${row.implementation_estimate_days}d` : "—"}</td>
        <td>
          <StateBadge state={row.status} />
        </td>
        <td className="dim" style={{ fontSize: 11.5 }}>{formatDate(row.created_at)}</td>
      </tr>
      {open && (
        <tr>
          <td colSpan={8} style={{ background: "var(--bg-panel)" }}>
            <dl className="kv">
              <dt>Discovery source</dt>
              <dd>{row.discovery_source.replace(/_/g, " ")}</dd>
              <dt>Feasibility</dt>
              <dd>{row.data_access_feasibility.replace(/_/g, " ")}</dd>
              <dt>Authentication</dt>
              <dd>{row.authentication_requirements.join(", ") || "—"}</dd>
              <dt>Required permissions</dt>
              <dd>{row.required_permissions.join(", ") || "—"}</dd>
              <dt>Risks</dt>
              <dd>
                {row.integration_risks.length === 0 ? (
                  "none recorded"
                ) : (
                  <ul style={{ margin: 0, paddingLeft: 16 }}>
                    {row.integration_risks.map((risk) => (
                      <li key={risk}>{risk}</li>
                    ))}
                  </ul>
                )}
              </dd>
            </dl>
          </td>
        </tr>
      )}
    </>
  );
}
