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
