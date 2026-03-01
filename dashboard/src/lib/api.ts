import type { ProjectListResponse, GlobalBudgetResponse, ProjectBudgetResponse } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8787";

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    next: { revalidate: 30 },
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

export async function fetchHealth(): Promise<{ status: string }> {
  return apiFetch<{ status: string }>("/health");
}
