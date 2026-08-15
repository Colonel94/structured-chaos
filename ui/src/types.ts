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

export interface CaseReview {
  case_id: string;
  channel: string;
  case_state: string;
  first_contact_at: string;
  fields: ReviewField[];
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
}

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
