/**
 * Tests for per-session budget enforcement.
 *
 * Ported from: tests/test_cost_guard.py
 */

import { describe, expect, it } from "vitest";
import { CostTracker } from "../src/cost-tracker.js";

describe("CostTracker", () => {
  it("starts with zero spent", () => {
    const tracker = new CostTracker(10.0);
    expect(tracker.totalSpent).toBe(0);
    expect(tracker.remaining).toBe(10.0);
  });

  it("records costs correctly", () => {
    const tracker = new CostTracker(10.0);
    tracker.recordCost(0.5);
    tracker.recordCost(1.0);
    expect(tracker.totalSpent).toBeCloseTo(1.5);
    expect(tracker.remaining).toBeCloseTo(8.5);
  });

  it("allows iteration when budget is available", () => {
    const tracker = new CostTracker(10.0);
    tracker.recordCost(1.0);
    const check = tracker.checkBudget("deepseek/deepseek-v3.2");
    expect(check.allowed).toBe(true);
    expect(check.spentUsd).toBeCloseTo(1.0);
  });

  it("blocks when budget is exhausted", () => {
    const tracker = new CostTracker(0.001); // Very small budget
    tracker.recordCost(0.001);
    const check = tracker.checkBudget("deepseek/deepseek-v3.2");
    expect(check.allowed).toBe(false);
    expect(check.warning).toContain("exhausted");
  });

  it("emits warning at 50% threshold", () => {
    const tracker = new CostTracker(10.0, { alertThresholdWarning: 0.5 });
    tracker.recordCost(5.5); // 55% of budget
    const check = tracker.checkBudget("deepseek/deepseek-v3.2");
    expect(check.allowed).toBe(true);
    expect(check.warning).toContain("WARNING");
    expect(check.warning).toContain("55%");
  });

  it("emits critical warning at 80% threshold", () => {
    const tracker = new CostTracker(10.0, { alertThresholdCritical: 0.8 });
    tracker.recordCost(8.5); // 85% of budget
    const check = tracker.checkBudget("deepseek/deepseek-v3.2");
    expect(check.allowed).toBe(true);
    expect(check.warning).toContain("CRITICAL");
    expect(check.warning).toContain("85%");
  });

  it("no warning below threshold", () => {
    const tracker = new CostTracker(10.0);
    tracker.recordCost(1.0); // 10% — well below warning
    const check = tracker.checkBudget("deepseek/deepseek-v3.2");
    expect(check.warning).toBe("");
  });

  it("resets correctly", () => {
    const tracker = new CostTracker(10.0);
    tracker.recordCost(5.0);
    tracker.reset(20.0);
    expect(tracker.totalSpent).toBe(0);
    expect(tracker.remaining).toBe(20.0);
  });

  it("handles free models (zero cost)", () => {
    const tracker = new CostTracker(1.0);
    const check = tracker.checkBudget("qwen/qwen3-coder:free");
    expect(check.allowed).toBe(true);
  });

  it("handles unknown model IDs gracefully", () => {
    const tracker = new CostTracker(10.0);
    const check = tracker.checkBudget("unknown/model");
    expect(check.allowed).toBe(true); // Should use conservative estimate
  });
});
