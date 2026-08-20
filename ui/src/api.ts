// Thin fetch client for the engine's review routes. The tenant is sent as X-Tenant-Id (the PoC
// convention — RLS is the real isolation boundary; see engine/app/api/routes.py). Same-origin in
// prod; via the Vite `/api` proxy in dev.

import type { CaseReview, CaseSummary } from "./types";

const TENANT_KEY = "adaptive-intake.tenant-id";
const REVIEWER_KEY = "adaptive-intake.reviewer-id";

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

function tenantOrThrow(): string {
  const tenant = getTenantId();
  if (!tenant) throw new Error("Set a tenant id first.");
  return tenant;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: { "X-Tenant-Id": tenantOrThrow() } });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? `Request failed (${res.status})`);
  }
  return (await res.json()) as T;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "X-Tenant-Id": tenantOrThrow(), "Content-Type": "application/json" },
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
export async function ingestCase(text: string, files: File[]): Promise<{ case_ids: string[] }> {
  const form = new FormData();
  form.append("text", text);
  for (const f of files) form.append("files", f);
  const res = await fetch("/api/ingest", {
    method: "POST",
    headers: { "X-Tenant-Id": tenantOrThrow() },
    body: form,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? `Request failed (${res.status})`);
  }
  return (await res.json()) as { case_ids: string[] };
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
    headers: { "X-Tenant-Id": tenantOrThrow() },
    body: form,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? `Request failed (${res.status})`);
  }
  return (await res.json()) as ObjectUploadResult;
}

/** Approve a case (the commit gate). One-way; only after this may a report be issued. */
export function commitCase(
  caseId: string,
  reviewerId: string,
): Promise<{ commit: { committed_at: string; committed_by: string } }> {
  return post(`/api/cases/${caseId}/commit`, { reviewer_id: reviewerId });
}

// Download URLs — the tenant travels in the header on fetch, but a plain <a> can't set one, so these
// are opened via an authenticated fetch→blob in the UI. Kept here as the single source of route truth.
export const reportUrl = (caseId: string): string => `/api/cases/${caseId}/report.pdf`;
export const registerCsvUrl = (): string => "/api/cases.csv";
export const docUrl = (docId: string): string => `/api/docs/${docId}`;

/** Fetch a tenant-scoped binary route (report/CSV/source blob) with the X-Tenant-Id header, as an
 *  object URL a browser can open or embed. The caller revokes it when done. */
export async function fetchBlobUrl(path: string): Promise<string> {
  const res = await fetch(path, { headers: { "X-Tenant-Id": tenantOrThrow() } });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? `Request failed (${res.status})`);
  }
  return URL.createObjectURL(await res.blob());
}
