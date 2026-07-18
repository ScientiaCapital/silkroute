export type Provider =
  | "deepseek"
  | "qwen"
  | "z-ai"
  | "moonshotai"
  | "ollama"
  | "anthropic"
  | "openai"
  | "google";
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

// Live GET /models catalog entry — a subset of ModelSpec's fields (the API
// doesn't serve param counts or recommendedFor), snake_case to mirror the
// FastAPI ModelResponse verbatim.
export interface ModelCatalogItem {
  model_id: string;
  name: string;
  provider: string;
  tier: ModelTier;
  input_cost_per_m: number;
  output_cost_per_m: number;
  context_window: number;
  max_output_tokens: number;
  capabilities: string[];
  supports_tool_calling: boolean;
  supports_streaming: boolean;
  is_moe: boolean;
  is_free: boolean;
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

export interface ModelCostSnapshotItem {
  project_id: string;
  model_id: string;
  provider: string;
  snapshot_date: string;
  total_cost_usd: number;
  total_requests: number;
  total_tokens: number;
}

export interface ModelCostSnapshotListResponse {
  snapshots: ModelCostSnapshotItem[];
  count: number;
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

// --- AV/Edge demo (GET /demo/room, GET /demo/stream) ---

export interface RoomState {
  device_name: string;
  model: string;
  firmware: string;
  state: string;
  uptime_seconds: number;
  recorder_name: string;
  recorder_state: string;
  duration_seconds: number;
  filename: string;
  cpu_percent: number;
  storage_free_bytes: number;
  devices_online: number;
  devices_total: number;
  recorders_active: number;
  healthy: boolean;
  source: string;
}

// One frame of the SSE agent trace. `type` selects which `data` shape applies.
export type TraceEventType =
  | "session_start"
  | "thought"
  | "tool_call"
  | "answer"
  | "session_complete";

export interface TraceEvent {
  type: TraceEventType;
  data: Record<string, unknown>;
}

// Self-healing loop frames (GET /demo/heal).
export type HealEventType = "heal_start" | "heal_step" | "heal_result";

export interface HealEvent {
  type: HealEventType;
  data: Record<string, unknown>;
}

// --- AutoResearch Ledger (GET /research/ledger) ---

export interface LedgerEntry {
  commit: string;
  score: number;
  pass_rate: number;
  coverage: number;
  status: string;
  description: string;
}

export interface LedgerSummaryResponse {
  entries: LedgerEntry[];
  counts: Record<string, number>;
  best: LedgerEntry | null;
  available: boolean;
}

// --- Persistent agent memories (GET /memories) ---

export interface MemoryItem {
  id: number;
  project_id: string | null;
  kind: string;
  content: string;
  importance: number;
  recall_count: number;
  created_at: string;
}

export interface MemoryListResponse {
  items: MemoryItem[];
  count: number;
  available: boolean;
}

export const HEAL_FAULTS = [
  "recorder_stopped",
  "signal_loss",
  "storage_full",
  "storage_unmounted",
  "device_offline",
  "cpu_overload",
] as const;
