/**
 * Chinese LLM model registry — 13 models across 3 tiers.
 *
 * Ported from: src/silkroute/providers/models.py
 * Pricing data as of February 2026. Updated monthly.
 */

import { Capability, ModelSpec, ModelTier, Provider } from "./types.js";

// ============================================================================
// TIER 1: FREE MODELS
// Rate-limited but zero cost — maximize usage for simple tasks
// ============================================================================

const QWEN3_CODER_FREE: ModelSpec = {
  modelId: "qwen/qwen3-coder:free",
  name: "Qwen3 Coder (Free)",
  provider: Provider.QWEN,
  tier: ModelTier.FREE,
  inputCostPerM: 0.0,
  outputCostPerM: 0.0,
  contextWindow: 262_144,
  maxOutputTokens: 65_536,
  capabilities: [Capability.CODING, Capability.TOOL_CALLING, Capability.LONG_CONTEXT],
  supportsToolCalling: true,
  supportsStreaming: true,
  totalParamsB: 480.0,
  activeParamsB: 35.0,
  isMoe: true,
  isFree: true,
  rateLimitRpm: 20,
  recommendedFor: ["simple_code_review", "docstring_generation", "test_writing"],
};

const DEEPSEEK_R1_FREE: ModelSpec = {
  modelId: "deepseek/deepseek-r1-0528:free",
  name: "DeepSeek R1 (Free)",
  provider: Provider.DEEPSEEK,
  tier: ModelTier.FREE,
  inputCostPerM: 0.0,
  outputCostPerM: 0.0,
  contextWindow: 128_000,
  maxOutputTokens: 64_000,
  capabilities: [Capability.REASONING, Capability.MATH, Capability.CODING],
  supportsToolCalling: true,
  supportsStreaming: true,
  totalParamsB: 685.0,
  activeParamsB: 37.0,
  isMoe: true,
  isFree: true,
  rateLimitRpm: 20,
  recommendedFor: ["simple_reasoning", "issue_triage", "commit_message_generation"],
};

const GLM_45_AIR_FREE: ModelSpec = {
  modelId: "z-ai/glm-4.5-air:free",
  name: "GLM-4.5 Air (Free)",
  provider: Provider.GLM,
  tier: ModelTier.FREE,
  inputCostPerM: 0.0,
  outputCostPerM: 0.0,
  contextWindow: 128_000,
  maxOutputTokens: 4_096,
  capabilities: [Capability.TOOL_CALLING, Capability.CREATIVE],
  supportsToolCalling: true,
  supportsStreaming: true,
  totalParamsB: 0,
  activeParamsB: 0,
  isMoe: false,
  isFree: true,
  rateLimitRpm: 20,
  recommendedFor: ["summarization", "template_responses", "status_checks"],
};

// ============================================================================
// TIER 2: STANDARD MODELS
// Cost-effective workhorses for daily agent operations
// ============================================================================

const DEEPSEEK_V3_2: ModelSpec = {
  modelId: "deepseek/deepseek-v3.2",
  name: "DeepSeek V3.2",
  provider: Provider.DEEPSEEK,
  tier: ModelTier.STANDARD,
  inputCostPerM: 0.25,
  outputCostPerM: 0.38,
  contextWindow: 128_000,
  maxOutputTokens: 64_000,
  capabilities: [Capability.CODING, Capability.REASONING, Capability.TOOL_CALLING, Capability.AGENTIC],
  supportsToolCalling: true,
  supportsStreaming: true,
  totalParamsB: 685.0,
  activeParamsB: 37.0,
  isMoe: true,
  isFree: false,
  rateLimitRpm: 0,
  recommendedFor: ["code_review", "pr_description", "bug_analysis", "refactoring"],
};

const QWEN3_235B: ModelSpec = {
  modelId: "qwen/qwen3-235b-a22b-2507",
  name: "Qwen3 235B",
  provider: Provider.QWEN,
  tier: ModelTier.STANDARD,
  inputCostPerM: 0.07,
  outputCostPerM: 0.46,
  contextWindow: 131_072,
  maxOutputTokens: 8_192,
  capabilities: [Capability.CODING, Capability.REASONING, Capability.TOOL_CALLING, Capability.LONG_CONTEXT],
  supportsToolCalling: true,
  supportsStreaming: true,
  totalParamsB: 235.0,
  activeParamsB: 22.0,
  isMoe: true,
  isFree: false,
  rateLimitRpm: 0,
  recommendedFor: ["code_review", "documentation", "general_analysis"],
};

const QWEN3_30B: ModelSpec = {
  modelId: "qwen/qwen3-30b-a3b",
  name: "Qwen3 30B-A3B",
  provider: Provider.QWEN,
  tier: ModelTier.STANDARD,
  inputCostPerM: 0.06,
  outputCostPerM: 0.22,
  contextWindow: 131_072,
  maxOutputTokens: 8_192,
  capabilities: [Capability.CODING, Capability.TOOL_CALLING],
  supportsToolCalling: true,
  supportsStreaming: true,
  totalParamsB: 30.0,
  activeParamsB: 3.0,
  isMoe: true,
  isFree: false,
  rateLimitRpm: 0,
  recommendedFor: ["lightweight_tasks", "formatting", "simple_edits"],
};

const GLM_47: ModelSpec = {
  modelId: "z-ai/glm-4.7",
  name: "GLM-4.7",
  provider: Provider.GLM,
  tier: ModelTier.STANDARD,
  inputCostPerM: 0.25,
  outputCostPerM: 1.0,
  contextWindow: 128_000,
  maxOutputTokens: 16_384,
  capabilities: [Capability.CODING, Capability.TOOL_CALLING, Capability.AGENTIC],
  supportsToolCalling: true,
  supportsStreaming: true,
  totalParamsB: 0,
  activeParamsB: 0,
  isMoe: false,
  isFree: false,
  rateLimitRpm: 0,
  recommendedFor: ["tool_heavy_tasks", "multi_step_workflows", "ci_debugging"],
};

// ============================================================================
// TIER 3: PREMIUM MODELS
// Maximum capability for complex reasoning and heavy coding
// ============================================================================

const DEEPSEEK_R1: ModelSpec = {
  modelId: "deepseek/deepseek-r1-0528",
  name: "DeepSeek R1",
  provider: Provider.DEEPSEEK,
  tier: ModelTier.PREMIUM,
  inputCostPerM: 0.4,
  outputCostPerM: 1.75,
  contextWindow: 128_000,
  maxOutputTokens: 64_000,
  capabilities: [Capability.REASONING, Capability.MATH, Capability.CODING, Capability.AGENTIC],
  supportsToolCalling: true,
  supportsStreaming: true,
  totalParamsB: 685.0,
  activeParamsB: 37.0,
  isMoe: true,
  isFree: false,
  rateLimitRpm: 0,
  recommendedFor: ["complex_debugging", "architecture_decisions", "security_review"],
};

const QWEN3_CODER: ModelSpec = {
  modelId: "qwen/qwen3-coder",
  name: "Qwen3 Coder 480B",
  provider: Provider.QWEN,
  tier: ModelTier.PREMIUM,
  inputCostPerM: 0.22,
  outputCostPerM: 0.95,
  contextWindow: 262_144,
  maxOutputTokens: 65_536,
  capabilities: [Capability.CODING, Capability.TOOL_CALLING, Capability.LONG_CONTEXT, Capability.AGENTIC],
  supportsToolCalling: true,
  supportsStreaming: true,
  totalParamsB: 480.0,
  activeParamsB: 35.0,
  isMoe: true,
  isFree: false,
  rateLimitRpm: 0,
  recommendedFor: ["heavy_refactoring", "new_feature_implementation", "codebase_migration"],
};

const GLM_5: ModelSpec = {
  modelId: "z-ai/glm-5",
  name: "GLM-5",
  provider: Provider.GLM,
  tier: ModelTier.PREMIUM,
  inputCostPerM: 1.0,
  outputCostPerM: 3.2,
  contextWindow: 128_000,
  maxOutputTokens: 16_384,
  capabilities: [
    Capability.CODING,
    Capability.REASONING,
    Capability.TOOL_CALLING,
    Capability.AGENTIC,
    Capability.CREATIVE,
  ],
  supportsToolCalling: true,
  supportsStreaming: true,
  totalParamsB: 745.0,
  activeParamsB: 44.0,
  isMoe: true,
  isFree: false,
  rateLimitRpm: 0,
  recommendedFor: ["agentic_workflows", "creative_content", "complex_tool_chains"],
};

const KIMI_K2: ModelSpec = {
  modelId: "moonshotai/kimi-k2",
  name: "Kimi K2",
  provider: Provider.MOONSHOT,
  tier: ModelTier.PREMIUM,
  inputCostPerM: 0.39,
  outputCostPerM: 1.9,
  contextWindow: 131_072,
  maxOutputTokens: 16_384,
  capabilities: [Capability.CODING, Capability.REASONING, Capability.TOOL_CALLING, Capability.AGENTIC],
  supportsToolCalling: true,
  supportsStreaming: true,
  totalParamsB: 1000.0,
  activeParamsB: 32.0,
  isMoe: true,
  isFree: false,
  rateLimitRpm: 0,
  recommendedFor: ["multi_step_agents", "long_horizon_tasks", "research"],
};

// ============================================================================
// LOCAL MODELS (Ollama — zero API cost)
// ============================================================================

const QWEN3_30B_LOCAL: ModelSpec = {
  modelId: "ollama/qwen3:30b-a3b",
  name: "Qwen3 30B (Local)",
  provider: Provider.OLLAMA,
  tier: ModelTier.FREE,
  inputCostPerM: 0.0,
  outputCostPerM: 0.0,
  contextWindow: 131_072,
  maxOutputTokens: 8_192,
  capabilities: [Capability.CODING, Capability.TOOL_CALLING],
  supportsToolCalling: true,
  supportsStreaming: true,
  totalParamsB: 30.0,
  activeParamsB: 3.0,
  isMoe: true,
  isFree: true,
  rateLimitRpm: 0,
  recommendedFor: ["local_simple_tasks", "offline_coding", "privacy_sensitive"],
};

const GLM4_9B_LOCAL: ModelSpec = {
  modelId: "ollama/glm4:9b",
  name: "GLM-4 9B (Local)",
  provider: Provider.OLLAMA,
  tier: ModelTier.FREE,
  inputCostPerM: 0.0,
  outputCostPerM: 0.0,
  contextWindow: 128_000,
  maxOutputTokens: 4_096,
  capabilities: [Capability.TOOL_CALLING, Capability.CREATIVE],
  supportsToolCalling: true,
  supportsStreaming: true,
  totalParamsB: 9.0,
  activeParamsB: 9.0,
  isMoe: false,
  isFree: true,
  rateLimitRpm: 0,
  recommendedFor: ["local_lightweight", "summaries", "drafts"],
};

// ============================================================================
// MODEL REGISTRY
// ============================================================================

/** All 13 Chinese models keyed by model ID. */
export const ALL_MODELS: ReadonlyMap<string, ModelSpec> = new Map([
  // Free tier
  [QWEN3_CODER_FREE.modelId, QWEN3_CODER_FREE],
  [DEEPSEEK_R1_FREE.modelId, DEEPSEEK_R1_FREE],
  [GLM_45_AIR_FREE.modelId, GLM_45_AIR_FREE],
  // Standard tier
  [DEEPSEEK_V3_2.modelId, DEEPSEEK_V3_2],
  [QWEN3_235B.modelId, QWEN3_235B],
  [QWEN3_30B.modelId, QWEN3_30B],
  [GLM_47.modelId, GLM_47],
  // Premium tier
  [DEEPSEEK_R1.modelId, DEEPSEEK_R1],
  [QWEN3_CODER.modelId, QWEN3_CODER],
  [GLM_5.modelId, GLM_5],
  [KIMI_K2.modelId, KIMI_K2],
  // Local
  [QWEN3_30B_LOCAL.modelId, QWEN3_30B_LOCAL],
  [GLM4_9B_LOCAL.modelId, GLM4_9B_LOCAL],
]);

/** Models grouped by tier. */
export const MODELS_BY_TIER: Readonly<Record<ModelTier, readonly ModelSpec[]>> = {
  [ModelTier.FREE]: [QWEN3_CODER_FREE, DEEPSEEK_R1_FREE, GLM_45_AIR_FREE, QWEN3_30B_LOCAL, GLM4_9B_LOCAL],
  [ModelTier.STANDARD]: [DEEPSEEK_V3_2, QWEN3_235B, QWEN3_30B, GLM_47],
  [ModelTier.PREMIUM]: [DEEPSEEK_R1, QWEN3_CODER, GLM_5, KIMI_K2],
};

/** Default routing preferences — first available wins. */
export const DEFAULT_ROUTING: Readonly<Record<ModelTier, readonly string[]>> = {
  [ModelTier.FREE]: [
    "qwen/qwen3-coder:free",
    "deepseek/deepseek-r1-0528:free",
    "z-ai/glm-4.5-air:free",
    "ollama/qwen3:30b-a3b",
    "ollama/glm4:9b",
  ],
  [ModelTier.STANDARD]: [
    "deepseek/deepseek-v3.2",
    "qwen/qwen3-235b-a22b-2507",
    "z-ai/glm-4.7",
    "qwen/qwen3-30b-a3b",
  ],
  [ModelTier.PREMIUM]: [
    "deepseek/deepseek-r1-0528",
    "qwen/qwen3-coder",
    "z-ai/glm-5",
    "moonshotai/kimi-k2",
  ],
};

/** Look up a model by ID. */
export function getModel(modelId: string): ModelSpec | undefined {
  return ALL_MODELS.get(modelId);
}

/** Get the cheapest model in a tier, optionally filtered by capability. */
export function getCheapestModel(tier: ModelTier, capability?: Capability): ModelSpec | undefined {
  let candidates = MODELS_BY_TIER[tier] ?? [];
  if (capability) {
    candidates = candidates.filter((m) => m.capabilities.includes(capability));
  }
  if (candidates.length === 0) return undefined;
  return candidates.reduce((cheapest, m) =>
    m.inputCostPerM + m.outputCostPerM < cheapest.inputCostPerM + cheapest.outputCostPerM ? m : cheapest,
  );
}

/** Estimate cost in USD for a given token count. */
export function estimateCost(model: ModelSpec, inputTokens: number, outputTokens: number): number {
  const inputCost = (inputTokens / 1_000_000) * model.inputCostPerM;
  const outputCost = (outputTokens / 1_000_000) * model.outputCostPerM;
  return inputCost + outputCost;
}
