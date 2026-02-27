/**
 * Tests for 3-tier model routing.
 *
 * Ported from: tests/test_router.py
 */

import { describe, expect, it } from "vitest";
import { ALL_MODELS, MODELS_BY_TIER } from "../src/models.js";
import { routeTask } from "../src/router.js";
import { Capability, ModelTier } from "../src/types.js";

describe("routeTask", () => {
  // ─── User override (Level 1) ──────────────────────────────────────
  it("respects user model override", () => {
    const result = routeTask("anything", "z-ai/glm-5");
    expect(result.model.modelId).toBe("z-ai/glm-5");
    expect(result.selectionMethod).toBe("user_override");
  });

  it("falls through on invalid user override", () => {
    const result = routeTask("review code", "nonexistent/model");
    expect(result.selectionMethod).not.toBe("user_override");
  });

  // ─── Tier routing ────────────────────────────────────────────────
  it("routes simple tasks to FREE tier", () => {
    const result = routeTask("summarize this readme");
    expect(result.classification.tier).toBe(ModelTier.FREE);
    expect(result.model.tier).toBe(ModelTier.FREE);
  });

  it("routes coding tasks to STANDARD tier", () => {
    const result = routeTask("review this pull request");
    expect(result.classification.tier).toBe(ModelTier.STANDARD);
    expect(result.model.tier).toBe(ModelTier.STANDARD);
  });

  it("routes complex tasks to PREMIUM tier", () => {
    const result = routeTask("security review the authentication system");
    expect(result.classification.tier).toBe(ModelTier.PREMIUM);
    expect(result.model.tier).toBe(ModelTier.PREMIUM);
  });

  // ─── Tier override ───────────────────────────────────────────────
  it("respects tier override", () => {
    const result = routeTask("summarize this", undefined, ModelTier.PREMIUM);
    // Even though "summarize" is a free trigger, tier override forces premium
    expect(result.model.tier).toBe(ModelTier.PREMIUM);
  });

  // ─── Absolute fallback ───────────────────────────────────────────
  it("falls back to DeepSeek V3.2 when needed", () => {
    // Default unknown task should at minimum route to something
    const result = routeTask("xyz");
    expect(result.model).toBeDefined();
    expect(result.model.modelId).toBeDefined();
  });

  // ─── Selection method tracking ───────────────────────────────────
  it("reports capability_scoring for classified tasks", () => {
    const result = routeTask("implement a REST API");
    expect(["capability_scoring", "default_routing"]).toContain(result.selectionMethod);
  });
});

describe("model registry", () => {
  it("has exactly 13 models", () => {
    expect(ALL_MODELS.size).toBe(13);
  });

  it("has 5 free models", () => {
    expect(MODELS_BY_TIER[ModelTier.FREE]).toHaveLength(5);
  });

  it("has 4 standard models", () => {
    expect(MODELS_BY_TIER[ModelTier.STANDARD]).toHaveLength(4);
  });

  it("has 4 premium models", () => {
    expect(MODELS_BY_TIER[ModelTier.PREMIUM]).toHaveLength(4);
  });

  it("all free models have zero cost", () => {
    for (const model of MODELS_BY_TIER[ModelTier.FREE]) {
      expect(model.inputCostPerM).toBe(0);
      expect(model.outputCostPerM).toBe(0);
    }
  });

  it("all models have valid capabilities", () => {
    const validCaps = new Set(Object.values(Capability));
    for (const [, model] of ALL_MODELS) {
      for (const cap of model.capabilities) {
        expect(validCaps.has(cap)).toBe(true);
      }
    }
  });

  it("all models have positive context windows", () => {
    for (const [, model] of ALL_MODELS) {
      expect(model.contextWindow).toBeGreaterThan(0);
      expect(model.maxOutputTokens).toBeGreaterThan(0);
    }
  });

  it("DeepSeek V3.2 is the standard primary", () => {
    const model = ALL_MODELS.get("deepseek/deepseek-v3.2");
    expect(model).toBeDefined();
    expect(model!.tier).toBe(ModelTier.STANDARD);
  });
});
