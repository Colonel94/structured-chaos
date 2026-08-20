import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useHotkeys } from "react-hotkeys-hook";
import AudioProvenance, { type AudioSegment } from "./AudioProvenance";
import ImageProvenance from "./ImageProvenance";
import {
  commitCase,
  docUrl,
  fetchBlobUrl,
  getCase,
  getReviewerId,
  getTenantId,
  ingestCase,
  listCases,
  recordCorrection,
  registerCsvUrl,
  reportUrl,
  setReviewerId,
  setTenantId,
} from "./api";
import {
  GOVERNED_ORDER,
  type CaseReview,
  type CaseSummary,
  type Citation,
  type ReviewField,
  type SourceDocument,
} from "./types";

// The review screen: the engine's first client. A reviewer clears a case in under 30 seconds from the
// keyboard, tracing every value to its exact source (sentence / audio segment / image region) and
// approving it — the commit gate, after which (and only after which) a report may issue (CLAUDE.md §3).

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function pct(conf: number | null): string {
  return conf === null ? "—" : `${Math.round(conf * 100)}%`;
}

/** A citation's source document, resolved so provenance can pick the right viewer by its mime. */
function docOf(cite: Citation, docs: Map<string, SourceDocument>): SourceDocument | undefined {
  return docs.get(cite.source_document_id);
}

// ---- provenance: the "where did this come from?" answer, per source modality ----

function useDocObjectUrl(docId: string | null): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!docId) {
      setUrl(null);
      return;
    }
    let live = true;
    let obj: string | null = null;
    fetchBlobUrl(docUrl(docId))
      .then((u) => {
        if (live) {
          obj = u;
          setUrl(u);
        } else {
          URL.revokeObjectURL(u);
        }
      })
      .catch(() => live && setUrl(null));
    return () => {
      live = false;
      if (obj) URL.revokeObjectURL(obj);
      setUrl(null);
    };
  }, [docId]);
  return url;
}

/** Audio provenance for the selected field: its utterance spans, played from the waveform. */
function AudioTrace({ docId, cites }: { docId: string; cites: Citation[] }) {
  const src = useDocObjectUrl(docId);
  const segments: AudioSegment[] = cites.map((c, i) => ({
    id: `${i}`,
    start: Number((c.locator as Record<string, number>).t_start),
    end: Number((c.locator as Record<string, number>).t_end),
  }));
  const [active, setActive] = useState<string | null>(segments.length ? "0" : null);
  if (!src) return <div className="detail__meta">loading audio…</div>;
  return (
    <AudioProvenance src={src} segments={segments} activeId={active} onSegmentClick={setActive} />
  );
}

/** Image-region provenance for the selected field: the OCR bboxes it was read from. */
function ImageTrace({ docId, cites }: { docId: string; cites: Citation[] }) {
  const src = useDocObjectUrl(docId);
  const boxes = cites.map((c, i) => {
    const b = (c.locator as Record<string, number[]>).bbox;
    return { id: `${i}`, x: b[0], y: b[1], w: b[2] - b[0], h: b[3] - b[1] };
  });
  const [active, setActive] = useState<string | null>(boxes.length ? "0" : null);
  if (!src) return <div className="detail__meta">loading image…</div>;
  return <ImageProvenance src={src} boxes={boxes} activeId={active} onBoxClick={setActive} />;
}

/** Route the selected field's citations to the right viewer(s). Text spans light up in the source-text
 * panel (handled by the caller); audio/image get their own player/overlay here. */
function ProvenanceTrace({
  field,
  docs,
}: {
  field: ReviewField;
  docs: Map<string, SourceDocument>;
}) {
  const byDoc = new Map<string, { doc: SourceDocument; cites: Citation[] }>();
  for (const c of field.provenance) {
    const doc = docOf(c, docs);
    if (!doc) continue;
    const entry = byDoc.get(doc.id) ?? { doc, cites: [] };
    entry.cites.push(c);
    byDoc.set(doc.id, entry);
  }
  const panels = [...byDoc.values()].map(({ doc, cites }) => {
    if (doc.mime.startsWith("audio/") && cites.some((c) => c.locator && "t_start" in c.locator)) {
      return <AudioTrace key={doc.id} docId={doc.id} cites={cites} />;
    }
    if (doc.mime.startsWith("image/") && cites.some((c) => c.locator && "bbox" in c.locator)) {
      return <ImageTrace key={doc.id} docId={doc.id} cites={cites} />;
    }
    return null;
  });
  const any = panels.some(Boolean);
  return any ? <div className="trace-panels">{panels}</div> : null;
}

// ---- governed field card ----

function confidenceLabel(field: ReviewField): string | null {
  if (field.source_kind === "correction") return "corrected";
  if (field.confidence !== null && field.confidence <= 0.5) return "needs review";
  return null;
}

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
      {field.confidence !== null && <span className="field__conf">{pct(field.confidence)}</span>}
      {flag && <span className={`chip chip--${flag.replace(/\s/g, "-")}`}>{flag}</span>}
    </button>
  );
}

/** The provenance + metadata detail for the selected field, plus inline correction (until committed). */
function FieldDetail({
  field,
  docs,
  editable,
  onCorrect,
}: {
  field: ReviewField;
  docs: Map<string, SourceDocument>;
  editable: boolean;
  onCorrect: (fieldPath: string, newValue: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);

  const begin = useCallback(() => {
    setDraft(formatValue(field.value));
    setEditing(true);
  }, [field.value]);

  // `e` from the case screen opens the editor for the selected field.
  useEffect(() => {
    setEditing(false);
  }, [field.field_path]);
  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);
  useHotkeys("e", () => editable && begin(), { enabled: editable }, [editable, begin]);

  async function save() {
    await onCorrect(field.field_path, draft);
    setEditing(false);
  }

  return (
    <div className="detail">
      <div className="detail__head">
        <h3 className="detail__title">{field.field_path.replace(/_/g, " ")}</h3>
        {editable && !editing && (
          <button type="button" className="ghost ghost--sm" onClick={begin}>
            edit
          </button>
        )}
      </div>

      {editing ? (
        <div className="edit">
          <input
            ref={inputRef}
            className="edit__input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void save();
              if (e.key === "Escape") setEditing(false);
            }}
          />
          <div className="edit__actions">
            <button type="button" onClick={() => void save()} className="primary">
              save correction
            </button>
            <button type="button" className="ghost" onClick={() => setEditing(false)}>
              cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="detail__value">{formatValue(field.value) || <em>not stated</em>}</div>
      )}

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

      <ProvenanceTrace field={field} docs={docs} />

      <div className="detail__meta">
        {field.model_version && <>model {field.model_version} · </>}
        {field.prompt_version && <>prompt {field.prompt_version} · </>}
        {field.confidence !== null && (
          <span title="class-calibrated reliability × grounding (per-class, not per-case)">
            confidence {field.confidence.toFixed(2)}
          </span>
        )}
      </div>
    </div>
  );
}

/** Highlight the selected field's text spans inside the normalised source text (sentence trace). */
function SourceText({ text, spans }: { text: string; spans: [number, number][] }) {
  if (!text) return <pre className="trace">— no normalised text —</pre>;
  if (spans.length === 0) return <pre className="trace">{text}</pre>;
  const ordered = [...spans].sort((a, b) => a[0] - b[0]);
  const parts: ReactNode[] = [];
  let cursor = 0;
  ordered.forEach(([start, end], i) => {
    const s = Math.max(0, Math.min(start, text.length));
    const e = Math.max(s, Math.min(end, text.length));
    if (s > cursor) parts.push(text.slice(cursor, s));
    parts.push(<mark key={i}>{text.slice(s, e)}</mark>);
    cursor = e;
  });
  if (cursor < text.length) parts.push(text.slice(cursor));
  return <pre className="trace">{parts}</pre>;
}

// ---- decision (priority/SLA/routing) ----

function DecisionBar({ review }: { review: CaseReview }) {
  const d = review.decision;
  if (!d) return <div className="decision decision--none">no decision computed yet</div>;
  return (
    <div className="decision">
      <span className={`pri pri--${d.priority}`}>{d.priority}</span>
      <span className="decision__route">
        route <b>{d.routing}</b>
      </span>
      <span className="decision__sla">
        SLA {d.sla_target_hours}h
        {d.sla_response_due_at ? ` · due ${new Date(d.sla_response_due_at).toLocaleString()}` : ""}
      </span>
      <span className="decision__why" title={d.matched_rule_id}>
        {d.rationale}
      </span>
    </div>
  );
}

// ---- one case ----

function CaseDetail({
  review,
  reviewer,
  onReload,
  onCommitted,
}: {
  review: CaseReview;
  reviewer: string;
  onReload: () => void;
  onCommitted: () => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [showJson, setShowJson] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const byPath = useMemo(() => new Map(review.fields.map((f) => [f.field_path, f])), [review]);
  const docs = useMemo(
    () => new Map(review.source_documents.map((d) => [d.id, d])),
    [review.source_documents],
  );
  const emergent = review.fields.filter((f) => f.layer === "emergent");
  const committed = review.commit !== null;

  // The keyboard order: governed fields present (review order), then emergent — j/k walk it.
  const selectable = useMemo(() => {
    const gov = GOVERNED_ORDER.filter((p) => byPath.has(p)) as string[];
    return [...gov, ...emergent.map((f) => f.field_path)];
  }, [byPath, emergent]);

  useEffect(() => setSelected(null), [review.case_id]);

  const move = useCallback(
    (delta: number) => {
      if (selectable.length === 0) return;
      const idx = selected ? selectable.indexOf(selected) : -1;
      const next = (idx + delta + selectable.length) % selectable.length;
      setSelected(selectable[next]);
    },
    [selectable, selected],
  );
  useHotkeys("j", () => move(1), [move]);
  useHotkeys("k", () => move(-1), [move]);

  const selectedField = selected ? byPath.get(selected) : undefined;

  // Text spans of the selected field, for the sentence trace in the source panel.
  const textSpans: [number, number][] = useMemo(() => {
    if (!selectedField) return [];
    return selectedField.provenance
      .filter((c) => c.locator && "char_start" in c.locator)
      .map((c) => [
        Number((c.locator as Record<string, number>).char_start),
        Number((c.locator as Record<string, number>).char_end),
      ]);
  }, [selectedField]);

  async function correct(fieldPath: string, newValue: string) {
    setBusy(true);
    setNote(null);
    try {
      await recordCorrection(review.case_id, fieldPath, newValue, reviewer);
      onReload();
    } catch (e) {
      setNote((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const commit = useCallback(async () => {
    if (committed || busy) return;
    if (!window.confirm("Approve this case? Nothing external is issued until you do — and this is final."))
      return;
    setBusy(true);
    setNote(null);
    try {
      await commitCase(review.case_id, reviewer);
      onCommitted();
    } catch (e) {
      setNote((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [committed, busy, review.case_id, reviewer, onCommitted]);
  useHotkeys("c", () => void commit(), [commit]);

  const downloadReport = useCallback(async () => {
    setNote(null);
    try {
      const url = await fetchBlobUrl(reportUrl(review.case_id));
      window.open(url, "_blank");
    } catch (e) {
      setNote((e as Error).message);
    }
  }, [review.case_id]);
  useHotkeys("r", () => committed && void downloadReport(), { enabled: committed }, [
    committed,
    downloadReport,
  ]);

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
        <div className="case__actions">
          {committed ? (
            <>
              <span className="badge badge--ok">
                approved · {review.commit?.committed_by}
              </span>
              <button type="button" className="primary" onClick={() => void downloadReport()}>
                report (r)
              </button>
            </>
          ) : (
            <button type="button" className="primary" disabled={busy} onClick={() => void commit()}>
              approve (c)
            </button>
          )}
          <button type="button" className="ghost" onClick={() => setShowJson((v) => !v)}>
            {showJson ? "hide JSON" : "JSON"}
          </button>
        </div>
      </header>

      <DecisionBar review={review} />
      {note && <div className="banner banner--error">{note}</div>}

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
          <SourceText text={review.normalised_text} spans={textSpans} />
        </div>

        <aside className="case__right">
          {selectedField ? (
            <FieldDetail
              field={selectedField}
              docs={docs}
              editable={!committed && !busy}
              onCorrect={correct}
            />
          ) : (
            <div className="detail detail--hint">
              Select a field (or press <kbd>j</kbd>) to trace its source.
            </div>
          )}
          {showJson && <pre className="json">{JSON.stringify(review, null, 2)}</pre>}
        </aside>
      </div>
    </section>
  );
}

// ---- register + app shell ----

/** Class-reliability-first: unapproved cases first, ordered by the case's lowest governed-field
 * confidence (a null sorts last among unapproved), approved cases below.
 *
 * HONEST SCOPE (owner review 2026-08-19): today's confidence is a per-CLASS calibrated reliability ×
 * grounding — two cases predicted the same class are indistinguishable except by grounding. So this is
 * class-level triage (it front-loads the least-reliable categories), NOT a per-case difficulty ranking.
 * A true per-instance "this case is hard" signal does not exist yet; do not present the queue as one. */
function reviewOrder(cases: CaseSummary[]): CaseSummary[] {
  const rank = (c: CaseSummary) => (c.committed_at ? 1 : 0);
  const conf = (c: CaseSummary) =>
    c.min_governed_confidence === null ? Number.POSITIVE_INFINITY : c.min_governed_confidence;
  return [...cases].sort((a, b) => rank(a) - rank(b) || conf(a) - conf(b));
}

/** Self-serve intake: paste the messiest real case (or drop files) and get a structured case back — no
 * form to fill, no developer in the room. This is the product surface the winning-condition opens with. */
function NewCaseModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (caseId: string) => void;
}) {
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!text.trim() && files.length === 0) {
      setError("Paste a case or add a file.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const { case_ids } = await ingestCase(text.trim(), files);
      if (case_ids.length) onCreated(case_ids[0]);
      else onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal" onClick={() => !busy && onClose()}>
      <div className="modal__card" onClick={(e) => e.stopPropagation()}>
        <h3>New case</h3>
        <p className="modal__hint">
          Paste the messiest real case you have — a complaint, a chat thread, an email. Or drop a file
          (voice note, photo, PDF). Nothing to fill in; the system structures it.
        </p>
        <textarea
          className="modal__text"
          placeholder="Paste the case here…"
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={busy}
          rows={8}
          autoFocus
        />
        <input
          type="file"
          multiple
          className="modal__file"
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
          disabled={busy}
        />
        {error && <div className="banner banner--error">{error}</div>}
        <div className="modal__actions">
          <button type="button" className="primary" onClick={() => void submit()} disabled={busy}>
            {busy ? "structuring…" : "submit case"}
          </button>
          <button type="button" className="ghost" onClick={onClose} disabled={busy}>
            cancel
          </button>
        </div>
        {busy && (
          <p className="modal__wait">Running extraction on your case — this takes a few seconds.</p>
        )}
      </div>
    </div>
  );
}

const params = new URLSearchParams(window.location.search);
const INITIAL_TENANT = params.get("tenant") ?? getTenantId();
const INITIAL_CASE = params.get("case");

export default function App() {
  const [tenant, setTenant] = useState(INITIAL_TENANT);
  const [reviewer, setReviewer] = useState(getReviewerId());
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  const [review, setReview] = useState<CaseReview | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(INITIAL_CASE);
  const [error, setError] = useState<string | null>(null);
  const [showHelp, setShowHelp] = useState(false);
  const [showNew, setShowNew] = useState(false);

  const ordered = useMemo(() => (cases ? reviewOrder(cases) : null), [cases]);

  const onCreated = useCallback((caseId: string) => {
    setShowNew(false);
    setSelectedId(caseId);
    void listCases()
      .then((d) => setCases(d.cases))
      .catch(() => {});
  }, []);

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

  const reloadCase = useCallback(() => {
    if (!selectedId) return;
    getCase(selectedId)
      .then(setReview)
      .catch((e) => setError((e as Error).message));
    void refresh(); // keep the register's confidence/committed badges live
  }, [selectedId, refresh]);

  useEffect(() => {
    if (INITIAL_TENANT) setTenantId(INITIAL_TENANT);
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

  // n/p walk the review queue (next/prev case, low-confidence-first).
  const moveCase = useCallback(
    (delta: number) => {
      if (!ordered || ordered.length === 0) return;
      const idx = selectedId ? ordered.findIndex((c) => c.case_id === selectedId) : -1;
      const next = (idx + delta + ordered.length) % ordered.length;
      setSelectedId(ordered[next].case_id);
    },
    [ordered, selectedId],
  );
  useHotkeys("n", () => moveCase(1), [moveCase]);
  useHotkeys("p", () => moveCase(-1), [moveCase]);
  useHotkeys("shift+slash", () => setShowHelp((v) => !v));
  useHotkeys("escape", () => setShowHelp(false));

  function applyTenant() {
    setTenantId(tenant);
    setReviewerId(reviewer);
    setSelectedId(null);
    setReview(null);
    void refresh();
  }

  async function exportCsv() {
    try {
      const url = await fetchBlobUrl(registerCsvUrl());
      const a = document.createElement("a");
      a.href = url;
      a.download = "register.csv";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <h1>Adaptive Intake — Review</h1>
        <div className="tenant">
          <input
            aria-label="reviewer id"
            className="tenant__reviewer"
            placeholder="reviewer"
            value={reviewer}
            onChange={(e) => setReviewer(e.target.value)}
            onBlur={() => setReviewerId(reviewer)}
          />
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
          <button type="button" className="ghost" onClick={() => setShowHelp((v) => !v)}>
            ? keys
          </button>
        </div>
      </header>

      {error && <div className="banner banner--error">{error}</div>}

      <div className="layout">
        <nav className="register">
          <div className="register__head">
            <span>review queue</span>
            <div className="register__head-actions">
              <button
                type="button"
                className="primary primary--sm"
                onClick={() => setShowNew(true)}
                disabled={!getTenantId()}
                title={getTenantId() ? "" : "set a tenant id first"}
              >
                + new case
              </button>
              <button type="button" className="ghost" onClick={() => void exportCsv()}>
                CSV
              </button>
              <button type="button" className="ghost" onClick={() => void refresh()}>
                refresh
              </button>
            </div>
          </div>
          {ordered && ordered.length > 0 && (
            <p className="register__basis">
              ordered by class reliability — least-reliable predicted class first
            </p>
          )}
          {ordered === null ? (
            <p className="empty">Set a tenant id to load cases.</p>
          ) : ordered.length === 0 ? (
            <div className="empty">
              <p>No cases yet.</p>
              <button type="button" className="primary" onClick={() => setShowNew(true)}>
                + submit your first case
              </button>
            </div>
          ) : (
            <ul>
              {ordered.map((c) => (
                <li key={c.case_id}>
                  <button
                    type="button"
                    className={`register__item${selectedId === c.case_id ? " register__item--active" : ""}`}
                    onClick={() => setSelectedId(c.case_id)}
                  >
                    <span className="register__top">
                      {c.priority && <span className={`pri pri--${c.priority}`}>{c.priority}</span>}
                      <span className="register__cat">{c.category ?? "—"}</span>
                      {c.committed_at ? (
                        <span className="badge badge--ok badge--sm">approved</span>
                      ) : (
                        <span
                          className="register__conf"
                          title="predicted-class reliability × grounding — a class-level signal, not a per-case difficulty score"
                        >
                          {pct(c.min_governed_confidence)}
                        </span>
                      )}
                    </span>
                    <span className="register__fault">{c.fault ?? "(no summary yet)"}</span>
                    <span className="register__sub">
                      {c.channel} · {c.field_count} fields
                      {c.routing ? ` · ${c.routing}` : ""}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </nav>

        <main className="main">
          {review ? (
            <CaseDetail
              review={review}
              reviewer={reviewer || "reviewer"}
              onReload={reloadCase}
              onCommitted={reloadCase}
            />
          ) : (
            <div className="placeholder">Select a case to review.</div>
          )}
        </main>
      </div>

      {showNew && <NewCaseModal onClose={() => setShowNew(false)} onCreated={onCreated} />}

      {showHelp && (
        <div className="help" onClick={() => setShowHelp(false)}>
          <div className="help__card" onClick={(e) => e.stopPropagation()}>
            <h3>keyboard</h3>
            <dl>
              <dt>j / k</dt>
              <dd>next / previous field</dd>
              <dt>n / p</dt>
              <dd>next / previous case</dd>
              <dt>e</dt>
              <dd>edit (correct) the selected field</dd>
              <dt>c</dt>
              <dd>approve the case (commit gate)</dd>
              <dt>r</dt>
              <dd>download the report (approved cases)</dd>
              <dt>?</dt>
              <dd>toggle this help</dd>
            </dl>
          </div>
        </div>
      )}
    </div>
  );
}
