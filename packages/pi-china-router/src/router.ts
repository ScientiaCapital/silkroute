/**
 * 3-tier model selection with 4-level cascade routing.
 *
 * Ported from: src/silkroute/agent/router.py
 *
 * Selection priority:
 *   1. User override (explicit model selection)
 *   2. Capability scoring (best match within tier)
 *   3. DEFAULT_ROUTING fallback chain
 *   4. Absolute fallback: DeepSeek V3.2
 */

import { classifyTask } from "./classifier.js";
import { ALL_MODELS, DEFAULT_ROUTING, MODELS_BY_TIER } from "./models.js";
import { Capability, ModelSpec, ModelTier, TaskClassification } from "./types.js";

const ABSOLUTE_FALLBACK = "deepseek/deepseek-v3.2";

/** Score a model against required capabilities. AGENTIC gets a bonus. */
function scoreModel(model: ModelSpec, requiredCapabilities: Capability[]): number {
  let score = 0;
  for (const cap of requiredCapabilities) {
    if (model.capabilities.includes(cap)) {
      score += 1;
    }
  }
  // Bonus for agentic capability (useful for agent-driven tasks)
  if (model.capabilities.includes(Capability.AGENTIC)) {
    score += 0.5;
  }
  return score;
}

/** Select the best model from a tier based on capability scoring. */
function selectByCapability(
  tier: ModelTier,
  capabilities: Capability[],
): ModelSpec | undefined {
  const candidates = MODELS_BY_TIER[tier] ?? [];
  if (candidates.length === 0) return undefined;

  let best: ModelSpec | undefined;
  let bestScore = -1;

  for (const model of candidates) {
    const score = scoreModel(model, capabilities);
    if (score > bestScore) {
      bestScore = score;
      best = model;
    }
  }

  return best;
}

/** Select a model using the DEFAULT_ROUTING preference chain. */
function selectByDefaultRouting(tier: ModelTier): ModelSpec | undefined {
  const chain = DEFAULT_ROUTING[tier] ?? [];
  for (const modelId of chain) {
    const model = ALL_MODELS.get(modelId);
    if (model) return model;
  }
  return undefined;
}

export interface RouteResult {
  model: ModelSpec;
  classification: TaskClassification;
  selectionMethod: "user_override" | "capability_scoring" | "default_routing" | "absolute_fallback";
}

/**
 * Route a task to the best Chinese LLM model.
 *
 * @param task - Natural language task description
 * @param userOverrideModelId - Explicit model selection by user (highest priority)
 * @param tierOverride - Force a specific tier instead of auto-classification
 */
export function routeTask(
  task: string,
  userOverrideModelId?: string,
  tierOverride?: ModelTier,
): RouteResult {
  const classification = classifyTask(task);
  const tier = tierOverride ?? classification.tier;

  // Level 1: User override
  if (userOverrideModelId) {
    const model = ALL_MODELS.get(userOverrideModelId);
    if (model) {
      return {
        model,
        classification,
        selectionMethod: "user_override",
      };
    }
  }

  // Level 2: Capability scoring
  const capModel = selectByCapability(tier, classification.capabilities);
  if (capModel) {
    return {
      model: capModel,
      classification,
      selectionMethod: "capability_scoring",
    };
  }

  // Level 3: DEFAULT_ROUTING fallback
  const defaultModel = selectByDefaultRouting(tier);
  if (defaultModel) {
    return {
      model: defaultModel,
      classification,
      selectionMethod: "default_routing",
    };
  }

  // Level 4: Absolute fallback
  const fallback = ALL_MODELS.get(ABSOLUTE_FALLBACK)!;
  return {
    model: fallback,
    classification,
    selectionMethod: "absolute_fallback",
  };
}
