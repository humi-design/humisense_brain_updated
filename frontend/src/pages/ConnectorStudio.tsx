/** Universal Connector Studio: build, validate and publish custom definitions. */

import { useState } from "react";
import { api, type CustomDefinition } from "../api/client";
import {
  Banner,
  Badge,
  Empty,
  ErrorNote,
  Loading,
  formatDate,
} from "../components/ui";
import { useApi, useAction } from "../lib/useApi";

const TEMPLATES: Record<string, Record<string, unknown>> = {
  rest: {
    base_url: "https://api.example.com/v1",
    auth: { type: "bearer_token" },
    resources: [
      {
        id: "items",
        path: "/items",
        items_path: "data.items",
        record_id_path: "id",
        updated_at_path: "updated_at",
        incremental_param: "updated_since",
        pagination: { strategy: "page", page_param: "page", size_param: "per_page" },
      },
    ],
  },
  graphql: {
    endpoint: "https://api.example.com/graphql",
    auth: { type: "bearer_token" },
    resources: [
      {
        id: "issues",
        query: "query($after: String) { issues(first: 50, after: $after) { nodes { id title updatedAt } pageInfo { hasNextPage endCursor } } }",
        items_path: "data.issues.nodes",
        record_id_path: "id",
        cursor_path: "data.issues.pageInfo.endCursor",
        has_next_path: "data.issues.pageInfo.hasNextPage",
      },
    ],
  },
  sql: {
    dialect: "postgresql",
    queries: [
      {
        id: "orders",
        sql: "SELECT id, status, updated_at FROM orders WHERE updated_at > :watermark ORDER BY updated_at",
        record_id_column: "id",
        updated_at_column: "updated_at",
      },
    ],
  },
  file: {
    transport: "local",
    allowed_roots: ["/srv/humisense/imports"],
    resources: [{ path: "/srv/humisense/imports/orders.csv", format: "csv", record_id_field: "id" }],
  },
  webhook: {
    signature_scheme: "sha256",
    events: ["issue.created", "issue.updated"],
    record_id_path: "id",
  },
};

const STAGES = ["draft", "pending_review", "approved", "published"];

export default function ConnectorStudio() {
  const definitions = useApi(() => api.listCustomDefinitions(), []);
  const kinds = useApi(() => api.listAdapterKinds(), []);

  const [name, setName] = useState("");
  const [kind, setKind] = useState("rest");
  const [json, setJson] = useState(JSON.stringify(TEMPLATES.rest, null, 2));
  const [generatedByAi, setGeneratedByAi] = useState(false);
  const [validation, setValidation] = useState<{ valid: boolean; errors: string[]; warnings: string[] } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);

  const validateAction = useAction((k: string, definition: Record<string, unknown>) =>
    api.validateCustomDefinition(k, definition),
  );
  const createAction = useAction((payload: Parameters<typeof api.createCustomDefinition>[0]) =>
    api.createCustomDefinition(payload),
  );
  const transitionAction = useAction((id: string, target: string) =>
    api.transitionCustomDefinition(id, target),
  );

  function parseJson(): Record<string, unknown> | null {
    try {
      return JSON.parse(json);
    } catch (err) {
      setError(new Error(`Definition is not valid JSON: ${(err as Error).message}`));
      return null;
    }
  }

  async function handleValidate() {
    setError(null);
    setNotice(null);
    const parsed = parseJson();
    if (!parsed) return;
    const result = await validateAction.run(kind, parsed);
    if (result) setValidation(result);
  }

  async function handleSave() {
    setError(null);
    setNotice(null);
    const parsed = parseJson();
    if (!parsed) return;
    if (!name.trim()) {
      setError(new Error("Give the connector definition a name."));
      return;
    }
    const result = await createAction.run({
      name,
      adapter_kind: kind,
      definition: parsed,
      generated_by_ai: generatedByAi,
    });
    if (result) {
      setNotice(`Saved "${result.name}" as a draft. It must pass review before it can be used.`);
      definitions.reload();
    }
  }

  return (
    <>
      <div className="page-head">
        <h1 className="page-title">Universal Connector Studio</h1>
        <p className="page-sub">
          Connect customer-specific systems with declarative definitions — REST, GraphQL, SQL,
          files and webhooks. Definitions are schema-validated and reviewed; no arbitrary code ever
          runs in the application process.
        </p>
      </div>

      {error && <ErrorNote error={error} />}
      {definitions.error && <ErrorNote error={definitions.error} />}
      {notice && <Banner tone="success">{notice}</Banner>}

      <Banner tone="warning">
        AI may help draft a definition, but AI-generated definitions never activate automatically.
        They must pass schema validation, sandbox testing and an authorised review before use.
      </Banner>

      <div className="grid grid-2">
        <div className="card">
          <div className="section-title" style={{ marginTop: 0 }}>
            Definition editor
          </div>

          <div className="field">
            <label className="label">Name</label>
            <input
              className="input"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. Acme MES (REST)"
            />
          </div>

          <div className="field">
            <label className="label">Adapter kind</label>
            <select
              className="select"
              value={kind}
              onChange={(event) => {
                setKind(event.target.value);
                setJson(JSON.stringify(TEMPLATES[event.target.value] ?? {}, null, 2));
                setValidation(null);
              }}
            >
              {(kinds.data ?? ["rest", "graphql", "sql", "file", "webhook"]).map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label className="label">Definition (JSON)</label>
            <textarea
              className="textarea"
              style={{ minHeight: 300 }}
              value={json}
              onChange={(event) => setJson(event.target.value)}
              spellCheck={false}
            />
          </div>

          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={generatedByAi}
              onChange={(event) => setGeneratedByAi(event.target.checked)}
            />
            This definition was drafted with AI assistance
          </label>

          <div className="row" style={{ marginTop: 14 }}>
            <button className="btn" disabled={validateAction.loading} onClick={handleValidate}>
              Validate
            </button>
            <span className="grow" />
            <button className="btn btn-primary" disabled={createAction.loading} onClick={handleSave}>
              Save as draft
            </button>
          </div>

          {validation && (
            <div style={{ marginTop: 14 }}>
              <Banner tone={validation.valid ? "success" : "danger"}>
                {validation.valid ? "Definition is valid." : "Definition has errors."}
              </Banner>
              {validation.errors.length > 0 && (
                <ul className="mono" style={{ color: "var(--danger)", paddingLeft: 16 }}>
                  {validation.errors.map((value) => (
                    <li key={value}>{value}</li>
                  ))}
                </ul>
              )}
              {validation.warnings.length > 0 && (
                <ul className="mono" style={{ color: "var(--warning)", paddingLeft: 16 }}>
                  {validation.warnings.map((value) => (
                    <li key={value}>{value}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        <div className="card">
          <div className="section-title" style={{ marginTop: 0 }}>
            Published definitions
          </div>
          {definitions.loading && <Loading rows={3} />}
          {definitions.data && definitions.data.length === 0 && (
            <Empty>No custom definitions yet.</Empty>
          )}
          <div className="stack">
            {(definitions.data ?? []).map((definition) => (
              <DefinitionCard
                key={definition.id}
                definition={definition}
                onTransition={async (target) => {
                  setNotice(null);
                  const result = await transitionAction.run(definition.id, target);
                  if (result) setNotice(`${result.name} → ${result.review_status}`);
                  definitions.reload();
                }}
              />
            ))}
          </div>
        </div>
      </div>
    </>
  );
}

function DefinitionCard({
  definition,
  onTransition,
}: {
  definition: CustomDefinition;
  onTransition: (target: string) => void;
}) {
  const index = STAGES.indexOf(definition.review_status);
  const next = index >= 0 && index < STAGES.length - 1 ? STAGES[index + 1] : null;
  const valid = definition.validation_report?.valid !== false;

  return (
    <div className="card" style={{ background: "var(--bg-panel)" }}>
      <div className="row-between">
        <div>
          <strong style={{ fontSize: 13 }}>{definition.name}</strong>
          <div className="dim" style={{ fontSize: 11.5 }}>
            {definition.adapter_kind} · v{definition.version} · {formatDate(definition.created_at)}
          </div>
        </div>
        <Badge
          tone={
            definition.review_status === "published"
              ? "success"
              : definition.review_status === "approved"
                ? "accent"
                : definition.review_status === "pending_review"
                  ? "info"
                  : "neutral"
          }
        >
          {definition.review_status.replace(/_/g, " ")}
        </Badge>
      </div>

      {!valid && (
        <Banner tone="danger">
          Validation failed: {(definition.validation_report.errors ?? []).join("; ")}
        </Banner>
      )}

      <div className="row wrap" style={{ gap: 4, marginTop: 8 }}>
        {STAGES.map((stage, stageIndex) => (
          <span
            key={stage}
            className="chip"
            style={{
              color: stageIndex <= index ? "var(--accent)" : "var(--text-dim)",
              borderColor: stageIndex <= index ? "var(--accent)" : "var(--border)",
            }}
          >
            {stage.replace(/_/g, " ")}
          </span>
        ))}
      </div>

      {next && (
        <div className="row" style={{ marginTop: 10 }}>
          <span className="grow" />
          <button
            className="btn btn-sm"
            disabled={!valid}
            title={valid ? undefined : "Fix validation errors before advancing"}
            onClick={() => onTransition(next)}
          >
            Advance to {next.replace(/_/g, " ")}
          </button>
        </div>
      )}
    </div>
  );
}
