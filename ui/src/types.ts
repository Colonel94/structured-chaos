// The review payload shapes — mirror engine/app/store/api.py (get_case_review / list_cases).

export interface Citation {
  source_document_id: string;
  role: string;
  locator: Record<string, unknown> | null;
}

export interface Correction {
  prev_value: unknown;
  reviewer_id: string;
  note: string | null;
}

export interface ReviewField {
  field_path: string;
  value: unknown;
  layer: "governed_core" | "emergent";
  head: string | null;
  qualifier: string | null;
  confidence: number | null;
  source_kind: "extraction" | "correction";
  correction: Correction | null;
  provenance: Citation[];
  model_version: string | null;
  prompt_version: string | null;
}

export interface SourceDocument {
  id: string;
  channel: string;
  mime: string;
  received_at: string;
}

// The deterministic priority/SLA/routing decision (Phase 6 rules engine) — explainable in one sentence.
export interface Decision {
  priority: string;
  routing: string;
  sla_target_hours: number;
  sla_response_due_at: string | null;
  matched_rule_id: string;
  rationale: string;
  policy_version: string;
}

// The human-approval stamp (Phase 7 commit gate). Present ⇒ approved; a report may then be issued.
export interface Commit {
  committed_at: string;
  committed_by: string;
}

// The synthesised agent-facing read — what this is / the discrepancy / why prioritised / the next
// step — assembled deterministically from the governed core + decision + any contradiction. A view,
// not a decision: the next_step is a pointer for the reviewer, never an action taken automatically.
export interface CaseAnalysis {
  headline: string;
  summary: string;
  discrepancy: string | null;
  priority_reason: string;
  next_step: string;
}

export interface CaseReview {
  case_id: string;
  channel: string;
  case_state: string;
  first_contact_at: string;
  fields: ReviewField[];
  decision: Decision | null;
  analysis: CaseAnalysis | null;
  commit: Commit | null;
  min_governed_confidence: number | null;
  normalised_text: string;
  source_documents: SourceDocument[];
}

export interface CaseSummary {
  case_id: string;
  channel: string;
  case_state: string;
  first_contact_at: string;
  category: string | null;
  fault: string | null;
  field_count: number;
  min_governed_confidence: number | null;
  priority: string | null;
  routing: string | null;
  sla_response_due_at: string | null;
  committed_at: string | null;
}

// The tenant's review-time aggregates (GET /api/review-stats) — the ≤30s load-bearing gate.
export interface ReviewStats {
  count: number;
  median_ms: number | null;
  p90_ms: number | null;
  avg_fields_edited: number;
}

// The allowed values per closed-vocabulary governed field (GET /api/field-options) — the one-key
// correction picks. Sourced from the extraction schema so they never drift from what the model emits.
export type FieldOptions = Record<string, string[]>;

// The governed core in review order — the small, stable, human-controlled layer (CLAUDE.md §4).
// A governed field absent from the payload is a refuse-to-guess absence (the customer never stated
// it), rendered explicitly rather than silently filled.
export const GOVERNED_ORDER = [
  "category",
  "fault",
  "desired_outcome",
  "severity_signal",
  "emotion_signal",
  "anchor_value",
] as const;
