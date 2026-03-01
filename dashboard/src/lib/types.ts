export type Provider = "deepseek" | "qwen" | "z-ai" | "moonshotai" | "ollama";
export type ModelTier = "free" | "standard" | "premium";
export type Capability = "coding" | "reasoning" | "tool_calling" | "long_context" | "multimodal" | "agentic" | "math" | "creative";

export interface ModelSpec {
  modelId: string;
  name: string;
  provider: Provider;
  tier: ModelTier;
  inputCostPerM: number;
  outputCostPerM: number;
  contextWindow: number;
  maxOutputTokens: number;
  capabilities: Capability[];
  supportsToolCalling: boolean;
  isMoe: boolean;
  isFree: boolean;
  totalParamsB: number;
  activeParamsB: number;
  recommendedFor: string[];
}

export interface BudgetSnapshot {
  projectId: string;
  projectName: string;
  budgetMonthlyUsd: number;
  spentThisMonth: number;
  remaining: number;
  status: "OK" | "WARNING" | "CRITICAL" | "EXCEEDED";
}

export interface DashboardStats {
  totalProjects: number;
  todaySpend: number;
  activeSessions: number;
  modelHealth: "healthy" | "degraded" | "down";
  freeRequestsPct: number;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  github_repo: string;
  budget_monthly_usd: number;
  budget_daily_usd: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectListResponse {
  projects: Project[];
  total: number;
}

export interface GlobalBudgetResponse {
  daily_spent_usd: number;
  daily_limit_usd: number;
  monthly_spent_usd: number;
  monthly_limit_usd: number;
  hourly_rate_usd: number;
  allowed: boolean;
  warning: string;
}

export interface ProjectBudgetResponse {
  project_id: string;
  monthly_spent_usd: number;
  daily_spent_usd: number;
  monthly_limit_usd: number | null;
}

export interface SupervisorStepSummary {
  id: string;
  name: string;
  status: string;
  cost_usd: number;
  output: string;
  error: string;
  retry_count: number;
}

export interface SupervisorSession {
  id: string;
  project_id: string;
  status: string;
  total_cost_usd: number;
  steps: SupervisorStepSummary[];
  created_at: string;
  updated_at: string;
  error: string;
}
