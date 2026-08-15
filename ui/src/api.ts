// Thin fetch client for the engine's review routes. The tenant is sent as X-Tenant-Id (the PoC
// convention — RLS is the real isolation boundary; see engine/app/api/routes.py). Same-origin in
// prod; via the Vite `/api` proxy in dev.

import type { CaseReview, CaseSummary } from "./types";

const TENANT_KEY = "adaptive-intake.tenant-id";

export function getTenantId(): string {
  return localStorage.getItem(TENANT_KEY) ?? "";
}

export function setTenantId(id: string): void {
  localStorage.setItem(TENANT_KEY, id.trim());
}

async function get<T>(path: string): Promise<T> {
  const tenant = getTenantId();
  if (!tenant) throw new Error("Set a tenant id first.");
  const res = await fetch(path, { headers: { "X-Tenant-Id": tenant } });
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
