// Thin same-origin client. Production scope and reviewer identity come from the secure session;
// the stored tenant id is display state and a dev-only compatibility header.

import type {
  CaseReview,
  CaseSummary,
  FeedbackEntry,
  FeedbackVerdict,
  FieldOptions,
  PromptDraft,
  ReviewStats,
  TuningDigest,
} from "./types";

const TENANT_KEY = "adaptive-intake.tenant-id";
const REVIEWER_KEY = "adaptive-intake.reviewer-id";

export interface AuthSession {
  authenticated: true;
  user: { id: string; email: string; display_name: string };
  workspace: { id: string; name: string; role: "admin" | "reviewer" };
}

function cookie(name: string): string {
  const prefix = `${encodeURIComponent(name)}=`;
  const part = document.cookie.split("; ").find((item) => item.startsWith(prefix));
  return part ? decodeURIComponent(part.slice(prefix.length)) : "";
}

function requestHeaders(json = false): Record<string, string> {
  const headers: Record<string, string> = {};
  const tenant = getTenantId();
  const csrf = cookie("adaptive_intake_csrf");
  if (tenant) headers["X-Tenant-Id"] = tenant;
  if (csrf) headers["X-CSRF-Token"] = csrf;
  if (json) headers["Content-Type"] = "application/json";
  return headers;
}

async function authRequest(path: string, body?: unknown): Promise<AuthSession> {
  const res = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? undefined : requestHeaders(true),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? `Request failed (${res.status})`);
  }
  const session = (await res.json()) as AuthSession;
  setTenantId(session.workspace.id);
  setReviewerId(session.user.display_name);
  return session;
}

export async function getAuthSession(): Promise<AuthSession | null> {
  const res = await fetch("/api/auth/session");
  if (res.status === 401) return null;
  if (!res.ok) {
    throw new Error(
      res.status === 404
        ? "The review service is out of date. Restart it with the current release before signing in."
        : "The review service is temporarily unavailable. Please try again.",
    );
  }
  const session = (await res.json()) as AuthSession;
  setTenantId(session.workspace.id);
  setReviewerId(session.user.display_name);
  return session;
}

export function signupAccount(input: {
  email: string;
  password: string;
  display_name: string;
  workspace_name: string;
}): Promise<AuthSession> {
  return authRequest("/api/auth/signup", input);
}

export function loginAccount(email: string, password: string): Promise<AuthSession> {
  return authRequest("/api/auth/login", { email, password });
}

export async function logoutAccount(): Promise<void> {
  const res = await fetch("/api/auth/logout", { method: "POST", headers: requestHeaders() });
  if (!res.ok) throw new Error(`Sign out failed (${res.status})`);
  setTenantId("");
  setReviewerId("");
}

export interface SystemHealth {
  status: string;
  env: string;
  worker: {
    status: "alive" | "down" | "unknown";
    detail?: string;
    last_beat_age_seconds?: number;
  };
}

/** Public operational readiness. This endpoint carries no tenant data and is used to keep the
 * first-run experience honest when intake processing is unavailable. */
export async function getSystemHealth(): Promise<SystemHealth> {
  const res = await fetch("/health");
  if (!res.ok) throw new Error(`Health check failed (${res.status})`);
  return (await res.json()) as SystemHealth;
}

export function getTenantId(): string {
  return localStorage.getItem(TENANT_KEY) ?? "";
}

export function setTenantId(id: string): void {
  localStorage.setItem(TENANT_KEY, id.trim());
}

// The reviewer identity stamped on corrections + approvals (PoC: a free-text operator id; real auth
// maps a session→reviewer later). Defaults to "reviewer" so the flow never blocks on an empty id.
export function getReviewerId(): string {
  return localStorage.getItem(REVIEWER_KEY) ?? "reviewer";
}

export function setReviewerId(id: string): void {
  localStorage.setItem(REVIEWER_KEY, id.trim() || "reviewer");
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: requestHeaders() });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? `Request failed (${res.status})`);
  }
  return (await res.json()) as T;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: requestHeaders(true),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? `Request failed (${res.status})`);
  }
  return (await res.json()) as T;
}

export function listCases(): Promise<{ cases: CaseSummary[] }> {
  return get<{ cases: CaseSummary[] }>("/api/cases");
}

export function getCase(caseId: string): Promise<CaseReview> {
  return get<CaseReview>(`/api/cases/${caseId}`);
}

/** Self-serve intake: submit a messy case (pasted text and/or dropped files) and get back the ids of
 *  the structured case(s). The browser sets the multipart boundary, so we must NOT set Content-Type. */
export async function ingestCase(
  text: string,
  files: File[],
): Promise<{ case_ids: string[]; status: "queued" }> {
  const form = new FormData();
  form.append("text", text);
  for (const f of files) form.append("files", f);
  const res = await fetch("/api/ingest", {
    method: "POST",
    headers: requestHeaders(),
    body: form,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? `Request failed (${res.status})`);
  }
  return (await res.json()) as { case_ids: string[]; status: "queued" };
}

/** Record a reviewer's correction to one field; returns the refreshed review (projection + decision). */
export function recordCorrection(
  caseId: string,
  fieldPath: string,
  newValue: unknown,
  reviewerId: string,
  note?: string,
): Promise<CaseReview> {
  return post<CaseReview>(`/api/cases/${caseId}/corrections`, {
    field_path: fieldPath,
    new_value: newValue,
    reviewer_id: reviewerId,
    note: note ?? null,
  });
}

export interface ObjectUploadResult {
  object_type: string;
  ingested: number;
  duplicates: number;
  keys_indexed: number;
  key_fields: string[];
  total: number;
}

/** Self-serve object store: upload an orders/bookings/assets export (CSV/JSON/JSONL). Returns what was
 *  ingested + the identifier columns the profiler discovered. Browser sets the multipart boundary. */
export async function uploadObjects(objectType: string, file: File): Promise<ObjectUploadResult> {
  const form = new FormData();
  form.append("object_type", objectType);
  form.append("file", file);
  const res = await fetch("/api/objects", {
    method: "POST",
    headers: requestHeaders(),
    body: form,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? `Request failed (${res.status})`);
  }
  return (await res.json()) as ObjectUploadResult;
}

/** Approve a case (the commit gate). One-way past the undo window; only after this may a report be
 *  issued. `reviewMs`/`fieldsEdited` are the client-measured cost of clearing the case — logged for the
 *  ≤30s review-time gate. Returns the undo window so the UI can offer a brief undo. */
export function commitCase(
  caseId: string,
  reviewerId: string,
  reviewMs?: number,
  fieldsEdited?: number,
): Promise<{
  commit: { committed_at: string; committed_by: string };
  undo_window_seconds: number;
}> {
  return post(`/api/cases/${caseId}/commit`, {
    reviewer_id: reviewerId,
    review_ms: reviewMs ?? null,
    fields_edited: fieldsEdited ?? 0,
  });
}

/** Undo a just-approved case, within the server's grace window. 409 once the window has passed. */
export function uncommitCase(caseId: string, reviewerId: string): Promise<{ uncommitted: unknown }> {
  return post(`/api/cases/${caseId}/uncommit`, { reviewer_id: reviewerId });
}

/** The tenant's review-time aggregates — the ≤30s gate the whole review UI is optimised against. */
export function getReviewStats(): Promise<ReviewStats> {
  return get<ReviewStats>("/api/review-stats");
}

/** The tuning digest — the feedback loop's actionable end: recurring correction transitions, per-field
 *  edit pressure + time, feedback tally/notes, and the headline review median. "What to fix next." */
export function getTuningDigest(): Promise<TuningDigest> {
  return get<TuningDigest>("/api/tuning-digest");
}

/** Ask the local model to pre-draft a prompt-delta from the digest signal — a DRAFT for review, never
 *  applied. Slow (a local model call). */
export function draftPromptDelta(): Promise<PromptDraft> {
  return post<PromptDraft>("/api/tuning-digest/draft", {});
}

/** Give feedback on the model's extraction for a case (the feedback loop) — a verdict + optional note,
 *  independent of correcting a field or approving. Returns the recorded entry. */
export function postFeedback(
  caseId: string,
  verdict: FeedbackVerdict,
  comment: string,
  reviewerId: string,
): Promise<{ feedback: FeedbackEntry }> {
  return post(`/api/cases/${caseId}/feedback`, {
    verdict,
    comment: comment.trim() || null,
    reviewer_id: reviewerId,
  });
}

/** The allowed values per closed-vocabulary governed field — the one-key correction picks. Not tenant
 *  data, so no header; fetched once and cached by the caller. */
export async function getFieldOptions(): Promise<FieldOptions> {
  const res = await fetch("/api/field-options");
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return (await res.json()) as FieldOptions;
}

// Download URLs — the tenant travels in the header on fetch, but a plain <a> can't set one, so these
// are opened via an authenticated fetch→blob in the UI. Kept here as the single source of route truth.
export const reportUrl = (caseId: string): string => `/api/cases/${caseId}/report.pdf`;
export const registerCsvUrl = (): string => "/api/cases.csv";
export const docUrl = (docId: string): string => `/api/docs/${docId}`;

/** Fetch a tenant-scoped binary route (report/CSV/source blob) with the X-Tenant-Id header, as an
 *  object URL a browser can open or embed. The caller revokes it when done. */
export async function fetchBlobUrl(path: string): Promise<string> {
  const res = await fetch(path, { headers: requestHeaders() });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? `Request failed (${res.status})`);
  }
  return URL.createObjectURL(await res.blob());
}
