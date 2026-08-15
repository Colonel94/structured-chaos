import { useCallback, useEffect, useState } from "react";
import { getCase, getTenantId, listCases, setTenantId } from "./api";
import {
  GOVERNED_ORDER,
  type CaseReview,
  type CaseSummary,
  type ReviewField,
} from "./types";

// The review screen: the engine's first client. It reads the assembled case (governed core +
// emergent attributes) and makes every value traceable to its source in one click — the trust gate
// that a reviewer can answer "where did this come from?" without leaving the screen (CLAUDE.md §3).

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function confidenceLabel(field: ReviewField): string | null {
  if (field.source_kind === "correction") return "corrected";
  if (field.confidence !== null && field.confidence <= 0.5) return "needs review";
  return null;
}

/** One governed-core field, or an explicit refuse-to-guess absence when the model stated nothing. */
function GovernedField({
  path,
  field,
  onSelect,
  active,
}: {
  path: string;
  field: ReviewField | undefined;
  onSelect: () => void;
  active: boolean;
}) {
  const label = path.replace(/_/g, " ");
  if (!field) {
    return (
      <div className="field field--absent">
        <div className="field__label">{label}</div>
        <div className="field__value field__value--absent">not stated</div>
      </div>
    );
  }
  const flag = confidenceLabel(field);
  const wide = path === "fault" ? " field--wide" : "";
  return (
    <button
      type="button"
      className={`field field--button${wide}${active ? " field--active" : ""}`}
      onClick={onSelect}
    >
      <div className="field__label">{label}</div>
      <div className="field__value">{formatValue(field.value)}</div>
      {flag && <span className={`chip chip--${flag.replace(/\s/g, "-")}`}>{flag}</span>}
    </button>
  );
}

/** The provenance + metadata detail for the selected field — the "where did this come from?" answer. */
function FieldDetail({ field }: { field: ReviewField }) {
  return (
    <div className="detail">
      <h3 className="detail__title">{field.field_path.replace(/_/g, " ")}</h3>
      {field.correction && (
        <div className="detail__diff">
          <span className="detail__diff-prev">{formatValue(field.correction.prev_value)}</span>
          <span className="detail__diff-arrow"> → </span>
          <span className="detail__diff-new">{formatValue(field.value)}</span>
          <div className="detail__meta">
            corrected by {field.correction.reviewer_id}
            {field.correction.note ? ` — ${field.correction.note}` : ""}
          </div>
        </div>
      )}
      <div className="detail__section">provenance</div>
      {field.provenance.length === 0 ? (
        <div className="detail__meta">no citations</div>
      ) : (
        <ul className="detail__prov">
          {field.provenance.map((c, i) => (
            <li key={i}>
              <span className={`chip chip--${c.role}`}>{c.role}</span>
              <code>{c.source_document_id.slice(0, 8)}</code>
              {c.locator && <span className="detail__meta"> {JSON.stringify(c.locator)}</span>}
            </li>
          ))}
        </ul>
      )}
      <div className="detail__meta">
        {field.model_version && <>model {field.model_version} · </>}
        {field.prompt_version && <>prompt {field.prompt_version} · </>}
        {field.confidence !== null && <>confidence {field.confidence.toFixed(2)}</>}
      </div>
    </div>
  );
}

function CaseDetail({ review }: { review: CaseReview }) {
  const [selected, setSelected] = useState<string | null>(null);
  const [showJson, setShowJson] = useState(false);
  const byPath = new Map(review.fields.map((f) => [f.field_path, f]));
  const emergent = review.fields.filter((f) => f.layer === "emergent");
  const selectedField = selected ? byPath.get(selected) : undefined;

  return (
    <section className="case">
      <header className="case__header">
        <div>
          <span className="case__id">case {review.case_id.slice(0, 8)}</span>
          <span className="case__meta">
            {review.channel} · {review.case_state} · first contact{" "}
            {new Date(review.first_contact_at).toLocaleString()}
          </span>
        </div>
        <button type="button" className="ghost" onClick={() => setShowJson((v) => !v)}>
          {showJson ? "hide JSON" : "view JSON"}
        </button>
      </header>

      <div className="case__body">
        <div className="case__left">
          <h2 className="section-title">governed core</h2>
          <div className="grid">
            {GOVERNED_ORDER.map((path) => (
              <GovernedField
                key={path}
                path={path}
                field={byPath.get(path)}
                active={selected === path}
                onSelect={() => setSelected(path)}
              />
            ))}
          </div>

          <h2 className="section-title">
            emergent attributes <span className="count">{emergent.length}</span>
          </h2>
          {emergent.length === 0 ? (
            <p className="empty">none extracted</p>
          ) : (
            <table className="attrs">
              <thead>
                <tr>
                  <th>head</th>
                  <th>qualifier</th>
                  <th>value</th>
                  <th>src</th>
                </tr>
              </thead>
              <tbody>
                {emergent.map((f) => (
                  <tr
                    key={f.field_path}
                    className={selected === f.field_path ? "attrs__row--active" : ""}
                    onClick={() => setSelected(f.field_path)}
                  >
                    <td>{f.head}</td>
                    <td className="muted">{f.qualifier ?? "—"}</td>
                    <td>{formatValue(f.value)}</td>
                    <td className="muted">{f.provenance.length}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h2 className="section-title">source text</h2>
          <pre className="trace">{review.normalised_text || "— no normalised text —"}</pre>
        </div>

        <aside className="case__right">
          {selectedField ? (
            <FieldDetail field={selectedField} />
          ) : (
            <div className="detail detail--hint">Select a field to trace its source.</div>
          )}
          {showJson && (
            <pre className="json">{JSON.stringify(review, null, 2)}</pre>
          )}
        </aside>
      </div>
    </section>
  );
}

// Deep-link support: `?tenant=<uuid>&case=<id>` opens a case directly (shareable review links, and
// what lets the register/detail load without retyping a tenant). URL wins over the stored tenant.
const params = new URLSearchParams(window.location.search);
const INITIAL_TENANT = params.get("tenant") ?? getTenantId();
const INITIAL_CASE = params.get("case");

export default function App() {
  const [tenant, setTenant] = useState(INITIAL_TENANT);
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  const [review, setReview] = useState<CaseReview | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(INITIAL_CASE);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const data = await listCases();
      setCases(data.cases);
    } catch (e) {
      setCases(null);
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    if (INITIAL_TENANT) setTenantId(INITIAL_TENANT); // persist a deep-linked tenant for the API layer
    if (getTenantId()) void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!selectedId) {
      setReview(null);
      return;
    }
    let live = true;
    getCase(selectedId)
      .then((r) => live && setReview(r))
      .catch((e) => live && setError((e as Error).message));
    return () => {
      live = false;
    };
  }, [selectedId]);

  function applyTenant() {
    setTenantId(tenant);
    setSelectedId(null);
    setReview(null);
    void refresh();
  }

  return (
    <div className="app">
      <header className="topbar">
        <h1>Adaptive Intake — Review</h1>
        <div className="tenant">
          <input
            aria-label="tenant id"
            placeholder="tenant id (UUID)"
            value={tenant}
            onChange={(e) => setTenant(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && applyTenant()}
          />
          <button type="button" onClick={applyTenant}>
            load
          </button>
        </div>
      </header>

      {error && <div className="banner banner--error">{error}</div>}

      <div className="layout">
        <nav className="register">
          <div className="register__head">
            <span>cases</span>
            <button type="button" className="ghost" onClick={() => void refresh()}>
              refresh
            </button>
          </div>
          {cases === null ? (
            <p className="empty">Set a tenant id to load cases.</p>
          ) : cases.length === 0 ? (
            <p className="empty">No cases yet.</p>
          ) : (
            <ul>
              {cases.map((c) => (
                <li key={c.case_id}>
                  <button
                    type="button"
                    className={`register__item${selectedId === c.case_id ? " register__item--active" : ""}`}
                    onClick={() => setSelectedId(c.case_id)}
                  >
                    <span className="register__cat">{c.category ?? "—"}</span>
                    <span className="register__fault">{c.fault ?? "(no summary yet)"}</span>
                    <span className="register__sub">
                      {c.channel} · {c.field_count} fields
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </nav>

        <main className="main">
          {review ? (
            <CaseDetail review={review} />
          ) : (
            <div className="placeholder">Select a case to review.</div>
          )}
        </main>
      </div>
    </div>
  );
}
