import type { ProjectListResponse, GlobalBudgetResponse, ProjectBudgetResponse, ModelCostSnapshotListResponse, SupervisorSession, ModelCatalogItem, LedgerSummaryResponse, MemoryListResponse } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8787";
// Server-only secret (no NEXT_PUBLIC_ prefix → never shipped to the browser).
// These fetches run in server components, so the token stays server-side.
// Lets the dashboard talk to an auth-on backend (SILKROUTE_API_KEY set).
const API_KEY = process.env.SILKROUTE_API_KEY;

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    next: { revalidate: 30 },
    headers: API_KEY ? { Authorization: `Bearer ${API_KEY}` } : undefined,
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export async function fetchProjects(): Promise<ProjectListResponse> {
  return apiFetch<ProjectListResponse>("/projects");
}

export async function fetchGlobalBudget(): Promise<GlobalBudgetResponse> {
  return apiFetch<GlobalBudgetResponse>("/budget");
}

export async function fetchProjectBudget(projectId: string): Promise<ProjectBudgetResponse> {
  return apiFetch<ProjectBudgetResponse>(`/budget/${encodeURIComponent(projectId)}`);
}

export async function fetchModelCosts(
  projectId: string,
  startDate?: string,
  endDate?: string
): Promise<ModelCostSnapshotListResponse> {
  const params = new URLSearchParams({ project_id: projectId });
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  return apiFetch<ModelCostSnapshotListResponse>(`/budget/models?${params}`);
}

export async function fetchHealth(): Promise<{ status: string }> {
  return apiFetch<{ status: string }>("/health");
}

export async function fetchSupervisorSessions(projectId?: string): Promise<SupervisorSession[]> {
  const params = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return apiFetch<SupervisorSession[]>(`/supervisor/sessions${params}`);
}

export async function fetchModels(): Promise<ModelCatalogItem[]> {
  return apiFetch<ModelCatalogItem[]>("/models");
}

export async function fetchLedger(): Promise<LedgerSummaryResponse> {
  return apiFetch<LedgerSummaryResponse>("/research/ledger");
}

export async function fetchMemories(projectId?: string): Promise<MemoryListResponse> {
  const params = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return apiFetch<MemoryListResponse>(`/memories${params}`);
}
