import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useHotkeys } from "react-hotkeys-hook";
import AudioProvenance, { type AudioSegment } from "./AudioProvenance";
import ImageProvenance from "./ImageProvenance";
import {
  commitBatch,
  commitCase,
  docUrl,
  draftPromptDelta,
  fetchBlobUrl,
  getCase,
  getFieldOptions,
  getReviewerId,
  getReviewStats,
  getTenantId,
  getTuningDigest,
  ingestCase,
  listCases,
  postFeedback,
  recordCorrection,
  registerCsvUrl,
  reportUrl,
  setReviewerId,
  setTenantId,
  uncommitCase,
  uploadObjects,
  type ObjectUploadResult,
} from "./api";
import {
  GOVERNED_ORDER,
  type CaseReview,
  type CaseSummary,
  type Citation,
  type FeedbackVerdict,
  type FieldOptions,
  type PromptDraft,
  type ReviewField,
  type ReviewStats,
  type SourceDocument,
  type TuningDigest,
} from "./types";

// The line above which a case is "clean" — i.e. the system flagged NOTHING on it for review. This is the
// SAME 0.5 line the whole UI already uses for the amber "needs review" flag (confBand/confidenceLabel/the
// register), so "clean" means exactly "no field fell to the needs-review flag" — an honest, reachable band,
// not an aspirational high-confidence claim (case confidence is a MIN of per-CLASS reliability × grounding
// and tops out well below 0.9, so a 0.85 floor would sit permanently empty — the §10 capped-input trap).
// A null confidence (no governed signal) is NOT clean — it goes to the needs-you band.
const CLEAN_BAND_FLOOR = 0.5;

/** ms → a compact human duration for the review-time HUD ("24s", "1m 30s", "—"). */
function fmtDuration(ms: number | null): string {
  if (ms === null || !Number.isFinite(ms)) return "—";
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

// The review screen — a verification INSTRUMENT (DESIGN.md). A reviewer clears a case in under 30s from
// the keyboard, tracing every value to its exact source (sentence / audio segment / image region) and
// approving it — the commit gate, after which (and only after which) a report may issue (CLAUDE.md §3).
// Design law: uncertainty is the single loud signal; everything else recedes.

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function pct(conf: number | null): string {
  return conf === null ? "—" : `${Math.round(conf * 100)}%`;
}

/** The confidence spine is DISCRETE, not a smooth fade (DESIGN.md §6): confidence is a per-class
 * calibrated reliability × grounding with only ~6 trusted values per field, so a continuous gradient
 * would imply a precision that doesn't exist. Five bands + a neutral "no confidence". A per-FIELD signal
 * only — never a per-case difficulty claim (the register's class-level ordering copy is untouched). */
function confBand(conf: number | null): string | null {
  if (conf === null) return null;
  if (conf <= 0.5) return "flag";
  if (conf <= 0.7) return "low";
  if (conf <= 0.85) return "mid";
  if (conf <= 0.95) return "high";
  return "sure";
}

/** A citation's source document, resolved so provenance can pick the right viewer by its mime. */
function docOf(cite: Citation, docs: Map<string, SourceDocument>): SourceDocument | undefined {
  return docs.get(cite.source_document_id);
}

/** Honour prefers-reduced-motion in JS-driven motion (the intake stage cycle). CSS handles the rest. */
function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () =>
      typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  useEffect(() => {
    if (typeof matchMedia === "undefined") return;
    const m = matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReduced(m.matches);
    m.addEventListener?.("change", onChange);
    return () => m.removeEventListener?.("change", onChange);
  }, []);
  return reduced;
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

// ---- governed field row ----

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
  changed,
}: {
  path: string;
  field: ReviewField | undefined;
  onSelect: () => void;
  active: boolean;
  changed: boolean;
}) {
  const label = path.replace(/_/g, " ");
  // A governed field absent from the payload is a refuse-to-guess absence — a first-class, deliberate
  // state, never an empty cell or an error (winning-condition §5; DESIGN.md §6).
  if (!field) {
    return (
      <div className="field field--absent">
        <div className="field__label">{label}</div>
        <div className="field__value field__value--absent">not stated</div>
        <span />
      </div>
    );
  }
  const flag = confidenceLabel(field);
  const band = confBand(field.confidence);
  const flagged = field.confidence !== null && field.confidence <= 0.5;
  const wide = path === "fault" ? " field--wide" : "";
  const bandClass = band ? ` field--conf-${band}` : "";
  return (
    <button
      type="button"
      className={`field field--button${wide}${bandClass}${active ? " field--active" : ""}${changed ? " field--changed" : ""}`}
      onClick={onSelect}
    >
      <div className="field__label">
        {label}
        {changed && (
          <span className="field__changed" title="changed since you last reviewed this case">
            changed
          </span>
        )}
      </div>
      <div className="field__value">{formatValue(field.value)}</div>
      {field.confidence !== null ? (
        <span className="field__conf" data-flagged={flagged}>
          {pct(field.confidence)}
        </span>
      ) : (
        <span className="field__conf">—</span>
      )}
      {flag && <span className={`field__flag chip chip--${flag.replace(/\s/g, "-")}`}>{flag}</span>}
    </button>
  );
}

/** The provenance + metadata detail for the selected field, plus inline correction (until committed).
 * For a closed-vocabulary governed field the allowed values are offered as ONE-KEY picks (1–9) — the
 * biggest single lever on review time: correcting a mis-classified field becomes a keystroke, not typing
 * (the plan's frontend #2). `options` are the field's enum values from /api/field-options (honest: the
 * allowed set, not a claimed likelihood ranking — no per-value probability exists). */
function FieldDetail({
  field,
  docs,
  editable,
  options,
  onCorrect,
}: {
  field: ReviewField;
  docs: Map<string, SourceDocument>;
  editable: boolean;
  options: string[] | undefined;
  onCorrect: (fieldPath: string, newValue: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);

  const begin = useCallback(() => {
    setDraft(formatValue(field.value));
    setEditing(true);
  }, [field.value]);

  // The one-key picks: the allowed values minus the current one, capped at 9 (digit keys), first-9 shown.
  const picks = useMemo(() => {
    if (!options) return [];
    const current = formatValue(field.value);
    return options.filter((o) => o !== current).slice(0, 9);
  }, [options, field.value]);

  // `e` from the case screen opens the editor for the selected field.
  useEffect(() => {
    setEditing(false);
  }, [field.field_path]);
  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);
  useHotkeys("e", () => editable && begin(), { enabled: editable }, [editable, begin]);

  // 1–9 pick a value for a closed-vocab field without typing (disabled while the free-text editor is open,
  // so a digit typed into the input isn't stolen).
  useHotkeys(
    "1,2,3,4,5,6,7,8,9",
    (e) => {
      const idx = Number((e as KeyboardEvent).key) - 1;
      if (idx >= 0 && idx < picks.length) void onCorrect(field.field_path, picks[idx]);
    },
    { enabled: editable && !editing && picks.length > 0 },
    [editable, editing, picks, field.field_path, onCorrect],
  );

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

      {editable && !editing && picks.length > 0 && (
        <div className="picks">
          <div className="picks__label">correct to — press the number</div>
          <div className="picks__row">
            {picks.map((p, i) => (
              <button
                key={p}
                type="button"
                className="pick"
                onClick={() => void onCorrect(field.field_path, p)}
              >
                <span className="pick__key">{i + 1}</span>
                {p.replace(/_/g, " ")}
              </button>
            ))}
          </div>
        </div>
      )}

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
            <button type="button" onClick={() => void save()} className="primary primary--sm">
              save correction
            </button>
            <button type="button" className="ghost ghost--sm" onClick={() => setEditing(false)}>
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

/** Highlight the selected field's text spans inside the normalised source text (sentence trace). The
 * source panel is the ONE place the human's verbatim words appear — set in serif, as a document under
 * examination (DESIGN.md §2). Never a field value or model output. */
function SourceText({ text, spans }: { text: string; spans: [number, number][] }) {
  if (!text) return <pre className="trace trace--empty">— no normalised text —</pre>;
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

// ---- decision (priority/SLA/routing) — the rules engine speaking, distinct + authoritative ----

function DecisionBar({ review }: { review: CaseReview }) {
  const d = review.decision;
  if (!d)
    return (
      <div className="decision decision--none">
        <span className="decision__tag">RULES</span> no decision computed yet
      </div>
    );
  return (
    <div className="decision">
      <span className="decision__tag">RULES</span>
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

// ---- the synthesised read: what this is / discrepancy / next step (analysis, not just logged fields) ----

function AnalysisPanel({ review }: { review: CaseReview }) {
  const a = review.analysis;
  if (!a) return null;
  return (
    <div className="analysis">
      <div className="analysis__headline">{a.headline}</div>
      <p className="analysis__summary">{a.summary}</p>
      {a.discrepancy && (
        <div className="analysis__flag">
          <span className="analysis__tag analysis__tag--flag">discrepancy</span>
          {a.discrepancy}
        </div>
      )}
      <div className="analysis__next">
        <span className="analysis__tag">next step</span>
        {a.next_step}
      </div>
    </div>
  );
}

// ---- one case ----

/** The value of every field, keyed by path — the snapshot diff-on-return compares against, so a case that
 * REOPENS after new customer messages (re-extraction) highlights only what changed since the reviewer last
 * looked, instead of forcing them to re-read an unchanged case (the plan's frontend #5). */
function caseFingerprint(review: CaseReview): Record<string, string> {
  const fp: Record<string, string> = {};
  for (const f of review.fields) fp[f.field_path] = formatValue(f.value);
  return fp;
}
const seenKey = (caseId: string): string => `adaptive-intake.seen.${caseId}`;

const VERDICTS: { key: FeedbackVerdict; label: string; glyph: string }[] = [
  { key: "accurate", label: "accurate", glyph: "✓" },
  { key: "partial", label: "partial", glyph: "~" },
  { key: "inaccurate", label: "inaccurate", glyph: "✗" },
];

/** The FEEDBACK LOOP, made visible. Distinct from correcting a field (which fixes a value) and from
 * approving (which clears the case): here the reviewer tells the model how it did — a verdict + an
 * optional why. It's the qualitative signal that guides the next prompt/policy fix. Honest about where it
 * goes: collected as the model's eval + tuning set, $0, human-driven — never silent online learning. */
function FeedbackPanel({
  caseId,
  reviewer,
  feedback,
  onSubmitted,
}: {
  caseId: string;
  reviewer: string;
  feedback: CaseReview["feedback"];
  onSubmitted: () => void;
}) {
  const [verdict, setVerdict] = useState<FeedbackVerdict | null>(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Reset the draft when the case changes (prior verdicts still render from `feedback`).
  useEffect(() => {
    setVerdict(null);
    setComment("");
    setErr(null);
  }, [caseId]);

  async function submit(v: FeedbackVerdict) {
    setBusy(true);
    setErr(null);
    try {
      await postFeedback(caseId, v, comment, reviewer);
      setVerdict(null);
      setComment("");
      onSubmitted();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="feedback">
      <div className="feedback__head">
        <span className="feedback__title">feedback to the model</span>
        <span className="feedback__sub">how did the extraction do?</span>
      </div>
      <div className="feedback__verdicts">
        {VERDICTS.map((v) => (
          <button
            key={v.key}
            type="button"
            className={`verdict verdict--${v.key}${verdict === v.key ? " verdict--on" : ""}`}
            disabled={busy}
            // A verdict with no note submits on click; with a note, click sets it and "send" posts it.
            onClick={() => (comment.trim() ? setVerdict(v.key) : void submit(v.key))}
          >
            <span className="verdict__glyph">{v.glyph}</span>
            {v.label}
          </button>
        ))}
      </div>
      <textarea
        className="feedback__note"
        placeholder="optional — what did it get right or wrong, and why? (guides the next prompt fix)"
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        disabled={busy}
        rows={2}
      />
      {comment.trim() && (
        <button
          type="button"
          className="primary primary--sm"
          disabled={busy || !verdict}
          onClick={() => verdict && void submit(verdict)}
          title={verdict ? "" : "pick a verdict above first"}
        >
          {busy ? "sending…" : verdict ? `send "${verdict}" + note` : "pick a verdict above"}
        </button>
      )}
      {err && <div className="banner banner--error">{err}</div>}
      <p className="feedback__loop">
        Your feedback and field corrections are collected as the model’s eval + tuning set — they shape
        prompt and policy fixes. $0, human-driven; no data leaves.
      </p>
      {feedback.length > 0 && (
        <ul className="feedback__log">
          {feedback.map((f, i) => (
            <li key={i} className={`feedback__item feedback__item--${f.verdict}`}>
              <span className="feedback__verdict-tag">{f.verdict}</span>
              {f.comment && <span className="feedback__comment">{f.comment}</span>}
              <span className="feedback__meta">
                {f.reviewer_id} · {new Date(f.created_at).toLocaleString()}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function CaseDetail({
  review,
  reviewer,
  fieldOptions,
  reviewStats,
  onReload,
  onCommitted,
}: {
  review: CaseReview;
  reviewer: string;
  fieldOptions: FieldOptions;
  reviewStats: ReviewStats | null;
  onReload: () => void;
  onCommitted: () => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [showJson, setShowJson] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  // Review-time instrumentation: the clock starts when a case opens in front of a human (only the client
  // knows that) and is sent, with the edit count, at approval — the ≤30s gate (winning-condition §4).
  const openedAtRef = useRef<number>(Date.now());
  const [elapsed, setElapsed] = useState(0);
  const [edits, setEdits] = useState(0);
  // The undo window: a fresh approval is reversible for a few seconds, which is what makes single-key
  // commit safe (replaces the arm/confirm two-step — the owner-blessed long-term answer, DESIGN.md §10).
  const [undoUntil, setUndoUntil] = useState<number | null>(null);
  const [undoLeft, setUndoLeft] = useState(0);
  // Diff-on-return: which fields changed since this reviewer last saw the case.
  const [changed, setChanged] = useState<Set<string>>(() => new Set());

  const byPath = useMemo(() => new Map(review.fields.map((f) => [f.field_path, f])), [review]);
  const docs = useMemo(
    () => new Map(review.source_documents.map((d) => [d.id, d])),
    [review.source_documents],
  );
  const emergent = review.fields.filter((f) => f.layer === "emergent");
  const committed = review.commit !== null;
  // Processing died mid-pipeline (retries exhausted). The case must NOT read as a finished-but-empty
  // case — surface it as an error so a human picks it up; the source below is retained (originals are
  // immutable, §3), so the reviewer can still act on what the customer sent.
  const failed = review.case_state === "processing_failed";

  // The keyboard order: governed fields present (review order), then emergent — j/k walk it.
  const selectable = useMemo(() => {
    const gov = GOVERNED_ORDER.filter((p) => byPath.has(p)) as string[];
    return [...gov, ...emergent.map((f) => f.field_path)];
  }, [byPath, emergent]);

  // On entering a case: reset selection/undo, and diff current values against the last-seen snapshot
  // (diff-on-return), then persist the snapshot so a later return diffs against what they see now. Keyed
  // on case_id only — a reviewer's OWN correction reloads the same case and must not re-mark itself.
  useEffect(() => {
    setSelected(null);
    setUndoUntil(null);
    setEdits(0);
    let prev: Record<string, string> | null = null;
    try {
      prev = JSON.parse(localStorage.getItem(seenKey(review.case_id)) ?? "null");
    } catch {
      prev = null;
    }
    const now = caseFingerprint(review);
    const set = new Set<string>();
    if (prev) for (const [k, v] of Object.entries(now)) if (prev[k] !== v) set.add(k);
    setChanged(set);
    try {
      localStorage.setItem(seenKey(review.case_id), JSON.stringify(now));
    } catch {
      /* storage full/blocked — diff-on-return degrades to no highlight, never an error */
    }
    // review is intentionally read at case-entry only (not a dep) so own-edits don't re-trigger the diff.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [review.case_id]);

  // The live review clock — starts on case open, ticks while unapproved, freezes once approved/failed.
  useEffect(() => {
    openedAtRef.current = Date.now();
    setElapsed(0);
    if (review.commit !== null || review.case_state === "processing_failed") return;
    const t = window.setInterval(() => setElapsed(Date.now() - openedAtRef.current), 1000);
    return () => window.clearInterval(t);
  }, [review.case_id, review.commit, review.case_state]);

  // Count down the undo window; clear it when it lapses.
  useEffect(() => {
    if (undoUntil === null) return;
    const tick = () => {
      const left = Math.ceil((undoUntil - Date.now()) / 1000);
      if (left <= 0) {
        setUndoUntil(null);
        setUndoLeft(0);
      } else {
        setUndoLeft(left);
      }
    };
    tick();
    const t = window.setInterval(tick, 250);
    return () => window.clearInterval(t);
  }, [undoUntil]);

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
      setEdits((n) => n + 1); // the measured cost of this case (fields the reviewer had to fix)
      onReload();
    } catch (e) {
      setNote((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // Commit on a SINGLE keystroke (the fast path), made safe by the undo window rather than an arm/confirm
  // two-step: an accidental approval is reversible for a few seconds, then durable (DESIGN.md §10; the
  // owner-blessed successor to the c-arms/Enter gate). The measured review time + edit count go with it.
  const doCommit = useCallback(async () => {
    if (committed || busy || failed) return; // never approve a case that failed to process
    setBusy(true);
    setNote(null);
    const reviewMs = Date.now() - openedAtRef.current;
    try {
      const res = await commitCase(review.case_id, reviewer, reviewMs, edits);
      setUndoUntil(Date.now() + res.undo_window_seconds * 1000);
      onCommitted();
    } catch (e) {
      setNote((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [committed, busy, failed, review.case_id, reviewer, edits, onCommitted]);

  const doUndo = useCallback(async () => {
    setBusy(true);
    setNote(null);
    try {
      await uncommitCase(review.case_id, reviewer);
      setUndoUntil(null);
      openedAtRef.current = Date.now(); // resume the clock — the case is back under review
      onCommitted(); // reload → back to in_review
    } catch (e) {
      setNote((e as Error).message); // 409 once the window has passed — the approval stands
    } finally {
      setBusy(false);
    }
  }, [review.case_id, reviewer, onCommitted]);

  useHotkeys("c", () => void doCommit(), { enabled: !committed && !failed }, [
    doCommit,
    committed,
    failed,
  ]);
  useHotkeys("u", () => undoUntil !== null && void doUndo(), { enabled: undoUntil !== null }, [
    undoUntil,
    doUndo,
  ]);

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
    <section className={`case${committed ? " case--committed" : ""}${failed ? " case--failed" : ""}`}>
      <header className="case__header">
        <div className="case__headline-wrap">
          <span className="case__id">case {review.case_id.slice(0, 8)}</span>
          <span className="case__meta">
            {review.channel} · {failed ? "processing failed" : review.case_state} · first contact{" "}
            {new Date(review.first_contact_at).toLocaleString()}
          </span>
        </div>
        <div className="case__actions">
          {/* Review-time HUD — the live cost of this case + the tenant's running median (the ≤30s gate).
              A case over 30s reads amber, so the load-bearing number is visible while working, not after. */}
          {!failed && (
            <span
              className={`hud${!committed && elapsed > 30000 ? " hud--over" : ""}`}
              title="time on this case · your tenant's median time-to-approve (the ≤30s review-time gate)"
            >
              <span className="hud__now">⏱ {committed ? "done" : fmtDuration(elapsed)}</span>
              <span className="hud__sep">·</span>
              <span className="hud__med">
                median {fmtDuration(reviewStats?.median_ms ?? null)}
                {reviewStats && reviewStats.count > 0 ? ` (${reviewStats.count})` : ""}
              </span>
            </span>
          )}
          {failed ? (
            <span className="seal seal--fail">handle manually — nothing to approve</span>
          ) : committed ? (
            <>
              <span className="seal">
                <span className="seal__dot" />
                APPROVED · {review.commit?.committed_by}
              </span>
              <button type="button" className="primary" onClick={() => void downloadReport()}>
                report (r)
              </button>
            </>
          ) : (
            <button
              type="button"
              className="approve"
              disabled={busy}
              onClick={() => void doCommit()}
            >
              approve (c)
            </button>
          )}
          <button type="button" className="ghost" onClick={() => setShowJson((v) => !v)}>
            {showJson ? "hide JSON" : "JSON"}
          </button>
        </div>
      </header>

      {/* The undo toast — a brief, honest window to reverse a just-made approval before it is durable. */}
      {undoUntil !== null && (
        <div className="undo-toast" role="status">
          <span>
            Approved. Nothing external has been issued yet — you can still undo.
          </span>
          <button type="button" className="undo-toast__btn" disabled={busy} onClick={() => void doUndo()}>
            undo ({undoLeft}s) · u
          </button>
        </div>
      )}

      {failed && (
        <div className="banner banner--failed" role="alert">
          <strong>Processing didn&apos;t complete.</strong> Something broke while reading this case and
          the automatic retries were exhausted — so nothing here is trustworthy or complete. The
          customer&apos;s original message is retained below; handle this one by hand and re-run it if
          the underlying issue is fixed. It has not been auto-routed or resolved.
        </div>
      )}
      <DecisionBar review={review} />
      {/* The synthesis assumes a processed case — suppress it when processing failed, so a generic
          "A complaint / next step: action per the routed team" never contradicts the failure banner. */}
      {!failed && <AnalysisPanel review={review} />}
      {note && <div className="banner banner--error">{note}</div>}

      <div className="case__body">
        <div className="case__left">
          <div className="panel">
            <h2 className="section-title">Extracted details</h2>
            <div className="fields">
              {GOVERNED_ORDER.map((path) => (
                <GovernedField
                  key={path}
                  path={path}
                  field={byPath.get(path)}
                  active={selected === path}
                  changed={changed.has(path)}
                  onSelect={() => setSelected(path)}
                />
              ))}
            </div>
          </div>

          <div className="panel">
            <h2 className="section-title">
              Other details found <span className="count">{emergent.length}</span>
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
                      <td className="mono-cell">{f.head}</td>
                      <td className="muted">{f.qualifier ?? "—"}</td>
                      <td>{formatValue(f.value)}</td>
                      <td className="muted mono-cell">{f.provenance.length}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="panel">
            <h2 className="section-title">What the customer sent</h2>
            <div className="source">
              <SourceText text={review.normalised_text} spans={textSpans} />
            </div>
          </div>
        </div>

        <aside className="case__right">
          <div className="panel">
            {selectedField ? (
              <FieldDetail
                field={selectedField}
                docs={docs}
                editable={!committed && !busy}
                options={fieldOptions[selectedField.field_path]}
                onCorrect={correct}
              />
            ) : (
              <div className="detail detail--hint">
                Select a field (or press <kbd>j</kbd>) to trace its source — the exact sentence, audio
                segment, or image region it was read from.
              </div>
            )}
          </div>
          {!failed && (
            <FeedbackPanel
              caseId={review.case_id}
              reviewer={reviewer}
              feedback={review.feedback}
              onSubmitted={onReload}
            />
          )}
          {showJson && <pre className="json">{JSON.stringify(review, null, 2)}</pre>}
        </aside>
      </div>
    </section>
  );
}

// ---- register + app shell ----

/** Failed-first, then class-reliability: a case whose processing FAILED is surfaced at the top (it needs
 * a human now — a silently bottom-sorted error is not "surfaced"), then unapproved cases ordered by the
 * case's lowest governed-field confidence (a null sorts last among unapproved), then approved cases.
 *
 * HONEST SCOPE (owner review 2026-08-19): today's confidence is a per-CLASS calibrated reliability ×
 * grounding — two cases predicted the same class are indistinguishable except by grounding. So this is
 * class-level triage (it front-loads the least-reliable categories), NOT a per-case difficulty ranking.
 * A true per-instance "this case is hard" signal does not exist yet; do not present the queue as one. */
function reviewOrder(cases: CaseSummary[]): CaseSummary[] {
  const rank = (c: CaseSummary) =>
    c.case_state === "processing_failed" ? 0 : c.committed_at ? 2 : 1;
  const conf = (c: CaseSummary) =>
    c.min_governed_confidence === null ? Number.POSITIVE_INFINITY : c.min_governed_confidence;
  return [...cases].sort((a, b) => rank(a) - rank(b) || conf(a) - conf(b));
}

const INTAKE_STAGES = ["normalising", "transcribing", "extracting", "deciding"] as const;

/** The ~17s synchronous intake wait shows the PIPELINE working, not a generic spinner (DESIGN.md §6).
 * Honest: these are the real pipeline stages in order, advanced on a timer (the request has no progress
 * events) — stage labels, not telemetry. prefers-reduced-motion → shown statically, no cycle, no pulse. */
function IntakePipeline() {
  const reduced = usePrefersReducedMotion();
  const [stage, setStage] = useState(0);
  useEffect(() => {
    if (reduced) return;
    const t = window.setInterval(
      () => setStage((s) => (s + 1 < INTAKE_STAGES.length ? s + 1 : s)),
      3400,
    );
    return () => window.clearInterval(t);
  }, [reduced]);
  return (
    <div className="pipeline" role="status" aria-live="polite">
      {INTAKE_STAGES.map((label, i) => {
        const state = reduced
          ? "pipeline__row--active"
          : i < stage
            ? "pipeline__row--done"
            : i === stage
              ? "pipeline__row--active"
              : "";
        return (
          <div key={label} className={`pipeline__row ${state}`}>
            <span className="pipeline__dot" />
            <span className="pipeline__label">{label}…</span>
          </div>
        );
      })}
    </div>
  );
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
        {busy && <IntakePipeline />}
      </div>
    </div>
  );
}

/** Self-serve object store: connect orders/bookings/assets by file so a case's anchor resolves against
 * them (looked up, not asked — winning-condition §2, Moment 3). No schema declared; the profiler finds
 * the identifier columns. */
function ObjectStoreModal({ onClose }: { onClose: () => void }) {
  const [objectType, setObjectType] = useState("order");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ObjectUploadResult | null>(null);

  async function submit() {
    if (!file) {
      setError("Choose a CSV or JSON file.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setResult(await uploadObjects(objectType.trim() || "object", file));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const kind = objectType.trim() || "object";
  return (
    <div className="modal" onClick={() => !busy && onClose()}>
      <div className="modal__card" onClick={(e) => e.stopPropagation()}>
        <h3>Connect your data</h3>
        <p className="modal__hint">
          Upload your orders, bookings, or assets — a CSV or JSON export, however your system produces
          it. No schema to define; the system finds the identifiers itself. Once connected, a case that
          quotes an order number resolves against it — the drill looks facts up instead of asking.
        </p>
        <label className="modal__label">
          what are these?
          <input
            className="modal__type"
            value={objectType}
            onChange={(e) => setObjectType(e.target.value)}
            disabled={busy}
            placeholder="order"
          />
        </label>
        <input
          type="file"
          accept=".csv,.json,.jsonl,.ndjson"
          className="modal__file"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          disabled={busy}
        />
        {error && <div className="banner banner--error">{error}</div>}
        {result && (
          <div className="obj-result">
            Connected <b>{result.ingested}</b> new {kind}
            {result.ingested === 1 ? "" : "s"}
            {result.duplicates ? ` (${result.duplicates} already present)` : ""} — {result.total} total.
            <br />
            Identifiers found: <b>{result.key_fields.join(", ") || "—"}</b>.
          </div>
        )}
        <div className="modal__actions">
          <button type="button" className="primary" onClick={() => void submit()} disabled={busy}>
            {busy ? "connecting…" : "connect"}
          </button>
          <button type="button" className="ghost" onClick={onClose} disabled={busy}>
            {result ? "done" : "cancel"}
          </button>
        </div>
      </div>
    </div>
  );
}

/** The tuning digest — the feedback loop's ACTIONABLE end, for the owner/engineer (not the reviewer): it
 * clusters accumulated signal into "what to fix next" so the next prompt/policy change picks itself. The
 * recurring correction transitions are the headline — a repeated `from → to` names the exact boundary
 * reviewers keep re-drawing. Honest: it SURFACES the signal for a human; nothing is auto-applied, and on
 * self-authored gold a transition can mean the label was off, not the model (labelled inline). */
function TuningDigestModal({ onClose }: { onClose: () => void }) {
  const [digest, setDigest] = useState<TuningDigest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<PromptDraft | null>(null);
  const [drafting, setDrafting] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    getTuningDigest()
      .then(setDigest)
      .catch((e) => setError((e as Error).message));
  }, []);

  const fb = digest?.feedback;
  const hasSignal =
    !!digest &&
    (digest.correction_transitions.length > 0 ||
      (fb?.recent.some((f) => f.comment) ?? false));
  const empty =
    digest &&
    digest.correction_transitions.length === 0 &&
    digest.field_edits.length === 0 &&
    (!fb || fb.recent.length === 0);

  async function makeDraft() {
    setDrafting(true);
    setError(null);
    setCopied(false);
    try {
      setDraft(await draftPromptDelta());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDrafting(false);
    }
  }

  return (
    <div className="modal" onClick={onClose}>
      <div className="modal__card modal__card--wide" onClick={(e) => e.stopPropagation()}>
        <div className="digest__head">
          <h3>Tuning digest</h3>
          <span className="digest__sub">
            what to fix next — clustered from reviewer corrections + feedback
          </span>
        </div>
        {error && <div className="banner banner--error">{error}</div>}
        {!digest && !error && <p className="empty">loading…</p>}
        {empty && (
          <p className="empty">
            No corrections or feedback yet. As reviewers work, recurring corrections and their notes
            cluster here into the next prompt/policy fix.
          </p>
        )}
        {digest && !empty && (
          <>
            <div className="digest__headline">
              <span className="digest__stat">
                <b>{fmtDuration(digest.review.median_ms)}</b> median review time
                {digest.review.count > 0 ? ` · ${digest.review.count} approved` : ""}
              </span>
              {fb && Object.keys(fb.counts).length > 0 && (
                <span className="digest__verdicts">
                  {(["accurate", "partial", "inaccurate"] as const).map((v) =>
                    fb.counts[v] ? (
                      <span key={v} className={`digest__vtag digest__vtag--${v}`}>
                        {fb.counts[v]} {v}
                      </span>
                    ) : null,
                  )}
                </span>
              )}
            </div>

            {digest.correction_transitions.length > 0 && (
              <section className="digest__section">
                <h4 className="digest__title">
                  boundaries reviewers keep re-drawing
                  <span className="digest__hint">most-repeated correction, top of the backlog</span>
                </h4>
                <ul className="digest__transitions">
                  {digest.correction_transitions.map((t, i) => (
                    <li key={i} className="transition">
                      <span className="transition__count">×{t.count}</span>
                      <span className="transition__field">{t.field_path}</span>
                      <span className="transition__from">{t.from.replace(/_/g, " ")}</span>
                      <span className="transition__arrow">→</span>
                      <span className="transition__to">{t.to.replace(/_/g, " ")}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {digest.field_edits.length > 0 && (
              <section className="digest__section">
                <h4 className="digest__title">
                  where the editing effort goes
                  <span className="digest__hint">corrections · cases · median review time</span>
                </h4>
                <table className="digest__edits">
                  <tbody>
                    {digest.field_edits.map((e) => (
                      <tr key={e.field_path}>
                        <td className="mono-cell">{e.field_path}</td>
                        <td>
                          {e.corrections} correction{e.corrections === 1 ? "" : "s"}
                        </td>
                        <td className="muted">
                          {e.cases} case{e.cases === 1 ? "" : "s"}
                        </td>
                        <td className="muted mono-cell">{fmtDuration(e.median_ms)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            )}

            {fb && fb.recent.length > 0 && (
              <section className="digest__section">
                <h4 className="digest__title">recent feedback</h4>
                <ul className="digest__feedback">
                  {fb.recent
                    .filter((f) => f.comment)
                    .slice(0, 12)
                    .map((f, i) => (
                      <li key={i} className={`digest__fb digest__fb--${f.verdict}`}>
                        <span className="digest__vtag2">{f.verdict}</span>
                        <span className="digest__fbtext">{f.comment}</span>
                      </li>
                    ))}
                </ul>
              </section>
            )}

            <p className="digest__caveat">
              Surfaced for a human — nothing is auto-applied. A transition is a <em>reviewer
              correction</em> (what a person changed), not a proven model error: with an independent
              reviewer it’s real signal; on self-authored labels a flip can mean the label was off.
            </p>

            {hasSignal && (
              <section className="digest__section digest__draftbox">
                <div className="digest__drafthead">
                  <h4 className="digest__title">draft a prompt fix</h4>
                  <button
                    type="button"
                    className="primary primary--sm"
                    onClick={() => void makeDraft()}
                    disabled={drafting}
                  >
                    {drafting ? "drafting… (local model)" : draft ? "re-draft" : "draft from this signal"}
                  </button>
                </div>
                {draft?.draft ? (
                  <div className="draft">
                    <div className="draft__title">{draft.draft.title}</div>
                    <div className="draft__target">
                      target: <code>{draft.draft.target}</code>
                    </div>
                    <div className="draft__deltahead">
                      <span>proposed addition</span>
                      <button
                        type="button"
                        className="ghost ghost--sm"
                        onClick={() => {
                          void navigator.clipboard?.writeText(draft.draft?.delta ?? "");
                          setCopied(true);
                        }}
                      >
                        {copied ? "copied" : "copy"}
                      </button>
                    </div>
                    <pre className="draft__delta">{draft.draft.delta}</pre>
                    <div className="draft__rationale">{draft.draft.rationale}</div>
                    {draft.based_on.length > 0 && (
                      <div className="draft__basis">
                        <span className="draft__basis-label">grounded in</span>
                        {draft.based_on.map((b, i) => (
                          <span key={i} className="draft__chip">
                            {b}
                          </span>
                        ))}
                      </div>
                    )}
                    <ul className="draft__caveats">
                      {draft.caveats.map((c, i) => (
                        <li key={i}>{c}</li>
                      ))}
                    </ul>
                    <div className="draft__pr">
                      <div className="draft__deltahead">
                        <span>open it as a PR (runs the eval, human-merged)</span>
                        <button
                          type="button"
                          className="ghost ghost--sm"
                          onClick={() => {
                            void navigator.clipboard?.writeText(
                              `cd engine && uv run python scripts/open_tuning_pr.py --tenant ${getTenantId()}`,
                            );
                            setCopied(true);
                          }}
                        >
                          copy command
                        </button>
                      </div>
                      <pre className="draft__cmd">
                        cd engine && uv run python scripts/open_tuning_pr.py --tenant {getTenantId()}
                      </pre>
                      <p className="digest__caveat">
                        Run in your terminal — the engine never pushes to git or GitHub itself (it holds no
                        repo credentials). This opens a <code>tuning/…</code> PR with the delta; the
                        tuning-eval re-scores it; you review and merge. Nothing here is applied.
                      </p>
                    </div>
                  </div>
                ) : draft?.reason ? (
                  <p className="empty">{draft.reason}</p>
                ) : (
                  <p className="digest__caveat">
                    The local model proposes an additive clarification to the extraction prompt from the
                    signal above — a draft to review, never applied.
                  </p>
                )}
              </section>
            )}
          </>
        )}
        <div className="modal__actions">
          <button type="button" className="ghost" onClick={onClose}>
            close
          </button>
        </div>
      </div>
    </div>
  );
}

const params = new URLSearchParams(window.location.search);
const INITIAL_TENANT = params.get("tenant") ?? getTenantId();
const INITIAL_CASE = params.get("case");

// Theme — a light (Fluent / Power Platform) default with a dark swap; persisted, and honouring the OS
// preference on first visit. The theme is a `data-theme` attribute on <html> that flips CSS tokens only.
type Theme = "light" | "dark";
const THEME_KEY = "adaptive-intake.theme";
function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    /* storage blocked — fall through to the OS preference */
  }
  return typeof matchMedia !== "undefined" && matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}
// Apply before first paint so there's no light-then-dark flash on load.
if (typeof document !== "undefined") document.documentElement.setAttribute("data-theme", initialTheme());

export default function App() {
  const [tenant, setTenant] = useState(INITIAL_TENANT);
  const [reviewer, setReviewer] = useState(getReviewerId());
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  const [review, setReview] = useState<CaseReview | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(INITIAL_CASE);
  const [error, setError] = useState<string | null>(null);
  const [showHelp, setShowHelp] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [showObjects, setShowObjects] = useState(false);
  const [showTuning, setShowTuning] = useState(false);
  const [fieldOptions, setFieldOptions] = useState<FieldOptions>({});
  const [reviewStats, setReviewStats] = useState<ReviewStats | null>(null);
  const [batchBusy, setBatchBusy] = useState(false);
  const [theme, setTheme] = useState<Theme>(initialTheme);

  // Reflect the theme onto <html> (flips the CSS token set) and remember the choice.
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      /* storage blocked — the theme still applies this session */
    }
  }, [theme]);

  const ordered = useMemo(() => (cases ? reviewOrder(cases) : null), [cases]);

  // The triage split (the plan's frontend #3): CLEAN = an unapproved, non-failed case with NO field
  // flagged for review (every governed field above the 0.5 flag line) — the system raised no uncertainty
  // on it, so the reviewer can clear the whole band in one act; everything else NEEDS YOU. Honest: this is
  // "nothing flagged", a class-level band, not a per-case safety guarantee (§10 CORRECTION). Failed/
  // committed cases are in neither band.
  const clean = useMemo(
    () =>
      (ordered ?? []).filter(
        (c) =>
          !c.committed_at &&
          c.case_state !== "processing_failed" &&
          c.min_governed_confidence !== null &&
          c.min_governed_confidence > CLEAN_BAND_FLOOR,
      ),
    [ordered],
  );

  const refreshStats = useCallback(() => {
    if (!getTenantId()) return;
    void getReviewStats()
      .then(setReviewStats)
      .catch(() => setReviewStats(null));
  }, []);

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
    refreshStats(); // an approve/undo just moved the review-time median
  }, [selectedId, refresh, refreshStats]);

  // Approve a whole clean band at once — one human act clearing many cases (§3), the only way ≤30s/case
  // scales past a big queue. The batch's elapsed time is split evenly so the median stays honest.
  const batchStartRef = useRef<number>(Date.now());
  const approveClean = useCallback(async () => {
    if (clean.length === 0 || batchBusy) return;
    setBatchBusy(true);
    setError(null);
    const ms = Date.now() - batchStartRef.current;
    try {
      await commitBatch(
        clean.map((c) => c.case_id),
        reviewer || "reviewer",
        ms,
      );
      await refresh();
      refreshStats();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBatchBusy(false);
    }
  }, [clean, batchBusy, reviewer, refresh, refreshStats]);

  useEffect(() => {
    if (INITIAL_TENANT) setTenantId(INITIAL_TENANT);
    if (getTenantId()) {
      void refresh();
      refreshStats();
    }
    void getFieldOptions()
      .then(setFieldOptions)
      .catch(() => setFieldOptions({}));
  }, [refresh, refreshStats]);

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

  // n/p walk the review queue (next/prev case, class-reliability-first).
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
    batchStartRef.current = Date.now(); // the triage clock for this queue starts now
    void refresh();
    refreshStats();
    void getFieldOptions()
      .then(setFieldOptions)
      .catch(() => setFieldOptions({}));
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
        <div className="topbar__brand">
          <span className="topbar__mark mono" aria-hidden="true">
            ▚
          </span>
          <h1>Adaptive Intake — Review</h1>
        </div>
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
          <button type="button" className="load" onClick={applyTenant}>
            load
          </button>
          <button
            type="button"
            className="ghost"
            onClick={() => setShowObjects(true)}
            disabled={!getTenantId()}
            title={getTenantId() ? "connect your orders/bookings" : "set a tenant id first"}
          >
            connect data
          </button>
          <button
            type="button"
            className="ghost"
            onClick={() => setShowTuning(true)}
            disabled={!getTenantId()}
            title={getTenantId() ? "what to fix next — the feedback loop digest" : "set a tenant id first"}
          >
            tuning
          </button>
          <button
            type="button"
            className="ghost"
            onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
            title={theme === "dark" ? "switch to light theme" : "switch to dark theme"}
            aria-label="toggle light or dark theme"
          >
            {theme === "dark" ? "☀ light" : "☾ dark"}
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
              <button type="button" className="ghost ghost--sm" onClick={() => void exportCsv()}>
                CSV
              </button>
              <button type="button" className="ghost ghost--sm" onClick={() => void refresh()}>
                refresh
              </button>
            </div>
          </div>
          {ordered && ordered.length > 0 && (
            <p className="register__basis">
              ordered by class reliability — least-reliable predicted class first
            </p>
          )}
          {/* Triage: clear the high-reliability band in one act so a reviewer only ever opens cases that
              need them. Honest label — class-level band, not a per-case safety claim (§10). */}
          {clean.length > 0 && (
            <div className="triage">
              <span className="triage__count">
                {clean.length} with nothing flagged for review
              </span>
              <button
                type="button"
                className="triage__btn"
                onClick={() => void approveClean()}
                disabled={batchBusy}
                title="approve every case with no flagged field in one act — each is still your approval (§3)"
              >
                {batchBusy ? "approving…" : `approve all ${clean.length} clean`}
              </button>
            </div>
          )}
          {ordered === null ? (
            <div className="register__empty">
              <h4>No tenant loaded</h4>
              <p>Set a tenant id to load cases.</p>
            </div>
          ) : ordered.length === 0 ? (
            <div className="register__empty">
              <h4>An empty queue</h4>
              <p>
                This is where cases land for review — least-reliable first, each traceable to its
                source and approved by you. Nothing has come in yet.
              </p>
              <button type="button" className="primary primary--sm" onClick={() => setShowNew(true)}>
                + submit your first case
              </button>
            </div>
          ) : (
            <ul>
              {ordered.map((c) => {
                const flagged =
                  c.min_governed_confidence !== null && c.min_governed_confidence <= 0.5;
                const failedRow = c.case_state === "processing_failed";
                return (
                  <li key={c.case_id}>
                    <button
                      type="button"
                      className={`register__item${selectedId === c.case_id ? " register__item--active" : ""}${failedRow ? " register__item--failed" : ""}`}
                      onClick={() => setSelectedId(c.case_id)}
                    >
                      <span className="register__top">
                        {failedRow ? (
                          <span className="pri pri--P1">needs a human</span>
                        ) : (
                          c.priority && <span className={`pri pri--${c.priority}`}>{c.priority}</span>
                        )}
                        <span className="register__cat">
                          {failedRow ? "processing failed" : (c.category ?? "—")}
                        </span>
                        {failedRow ? (
                          <span className="badge--fail" title="processing failed — handle manually">
                            ⚠ error
                          </span>
                        ) : c.committed_at ? (
                          <span className="badge--sm">✓ approved</span>
                        ) : (
                          <span
                            className="register__conf"
                            data-flagged={flagged}
                            title="predicted-class reliability × grounding — a class-level signal, not a per-case difficulty score"
                          >
                            {pct(c.min_governed_confidence)}
                          </span>
                        )}
                      </span>
                      <span className="register__fault">
                        {failedRow
                          ? "We couldn't finish reading this — needs a person."
                          : (c.fault ?? "(no summary yet)")}
                      </span>
                      <span className="register__sub">
                        {c.channel} · {c.field_count} fields
                        {c.routing ? ` · ${c.routing}` : ""}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </nav>

        <main className="main">
          {review ? (
            <CaseDetail
              review={review}
              reviewer={reviewer || "reviewer"}
              fieldOptions={fieldOptions}
              reviewStats={reviewStats}
              onReload={reloadCase}
              onCommitted={reloadCase}
            />
          ) : (
            <div className="placeholder">Select a case to review.</div>
          )}
        </main>
      </div>

      {showNew && <NewCaseModal onClose={() => setShowNew(false)} onCreated={onCreated} />}
      {showObjects && <ObjectStoreModal onClose={() => setShowObjects(false)} />}
      {showTuning && <TuningDigestModal onClose={() => setShowTuning(false)} />}

      {showHelp && (
        <div className="help" onClick={() => setShowHelp(false)}>
          <div className="help__card" onClick={(e) => e.stopPropagation()}>
            <h3>keyboard</h3>
            <dl>
              <dt>j / k</dt>
              <dd>next / previous field</dd>
              <dt>n / p</dt>
              <dd>next / previous case</dd>
              <dt>1 – 9</dt>
              <dd>correct the selected field to a listed value (one key, no typing)</dd>
              <dt>e</dt>
              <dd>edit (correct) the selected field as free text</dd>
              <dt>c</dt>
              <dd>approve the case (undoable for a few seconds)</dd>
              <dt>u</dt>
              <dd>undo a just-made approval (within the window)</dd>
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
