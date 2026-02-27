/**
 * Core types for SilkRoute Chinese LLM routing.
 *
 * Ported from: src/silkroute/config/settings.py (ModelTier)
 *              src/silkroute/providers/models.py (Provider, Capability, ModelSpec)
 */

export enum ModelTier {
  FREE = "free",
  STANDARD = "standard",
  PREMIUM = "premium",
}

export enum Provider {
  DEEPSEEK = "deepseek",
  QWEN = "qwen",
  GLM = "z-ai",
  MOONSHOT = "moonshotai",
  OPENROUTER = "openrouter",
  OLLAMA = "ollama",
}

export enum Capability {
  CODING = "coding",
  REASONING = "reasoning",
  TOOL_CALLING = "tool_calling",
  LONG_CONTEXT = "long_context",
  MULTIMODAL = "multimodal",
  AGENTIC = "agentic",
  MATH = "math",
  CREATIVE = "creative",
}

export interface ModelSpec {
  /** OpenRouter-format ID (e.g., "deepseek/deepseek-v3.2") */
  modelId: string;
  /** Human-readable name */
  name: string;
  provider: Provider;
  tier: ModelTier;

  /** Pricing (USD per million tokens) */
  inputCostPerM: number;
  outputCostPerM: number;

  /** Capabilities */
  contextWindow: number;
  maxOutputTokens: number;
  capabilities: Capability[];
  supportsToolCalling: boolean;
  supportsStreaming: boolean;

  /** Architecture info */
  totalParamsB: number;
  activeParamsB: number;
  isMoe: boolean;

  /** Routing metadata */
  isFree: boolean;
  rateLimitRpm: number;
  recommendedFor: string[];
}

export interface TaskClassification {
  tier: ModelTier;
  capabilities: Capability[];
  confidence: number;
  reason: string;
}

export interface BudgetCheck {
  allowed: boolean;
  remainingUsd: number;
  spentUsd: number;
  limitUsd: number;
  warning: string;
}
