/**
 * @silkroute/pi-china-router
 *
 * Chinese LLM 3-tier routing extension for pi.dev.
 * 13 models across DeepSeek, Qwen, GLM, and Kimi.
 *
 * Public API:
 * - Model registry (ALL_MODELS, MODELS_BY_TIER, DEFAULT_ROUTING)
 * - Classifier (classifyTask)
 * - Router (routeTask)
 * - Types (ModelSpec, ModelTier, Capability, etc.)
 */

// Types
export {
  BudgetCheck,
  Capability,
  ModelSpec,
  ModelTier,
  Provider,
  TaskClassification,
} from "./types.js";

// Model registry
export {
  ALL_MODELS,
  DEFAULT_ROUTING,
  estimateCost,
  getCheapestModel,
  getModel,
  MODELS_BY_TIER,
} from "./models.js";

// Classifier
export { classifyTask } from "./classifier.js";

// Router
export { routeTask } from "./router.js";
export type { RouteResult } from "./router.js";
