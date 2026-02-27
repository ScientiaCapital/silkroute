/**
 * Per-session budget enforcement.
 *
 * Ported from: src/silkroute/agent/cost_guard.py
 *
 * Uses pi-ai's built-in token/cost tracking per response instead of
 * manually extracting costs from LiteLLM responses.
 */

import { estimateCost, getModel } from "@silkroute/pi-china-router";
import { BudgetCheck, BudgetConfig, DEFAULT_BUDGET_CONFIG } from "./types.js";

/** Estimated tokens per iteration for budget projection. */
const EST_INPUT_TOKENS = 2000;
const EST_OUTPUT_TOKENS = 1000;

export class CostTracker {
  private spentUsd = 0;
  private limitUsd: number;
  private config: BudgetConfig;

  constructor(limitUsd?: number, config?: Partial<BudgetConfig>) {
    this.limitUsd = limitUsd ?? DEFAULT_BUDGET_CONFIG.dailyMaxUsd;
    this.config = { ...DEFAULT_BUDGET_CONFIG, ...config };
  }

  /** Record cost from a completed LLM turn. */
  recordCost(costUsd: number): void {
    this.spentUsd += costUsd;
  }

  /** Get total spend so far. */
  get totalSpent(): number {
    return this.spentUsd;
  }

  /** Get remaining budget. */
  get remaining(): number {
    return this.limitUsd - this.spentUsd;
  }

  /**
   * Check if the session has enough budget for another iteration.
   *
   * Estimates the cost of one more iteration to decide if we can proceed.
   */
  checkBudget(modelId: string): BudgetCheck {
    const model = getModel(modelId);
    const nextCost = model
      ? estimateCost(model, EST_INPUT_TOKENS, EST_OUTPUT_TOKENS)
      : 0.01; // Conservative estimate for unknown models

    const remaining = this.limitUsd - this.spentUsd;

    // Check if we'd exceed the session budget
    if (remaining < nextCost) {
      return {
        allowed: false,
        remainingUsd: remaining,
        spentUsd: this.spentUsd,
        limitUsd: this.limitUsd,
        warning: `Budget exhausted: $${this.spentUsd.toFixed(4)} spent of $${this.limitUsd.toFixed(2)} limit`,
      };
    }

    // Check warning thresholds
    const usageFraction = this.limitUsd > 0 ? this.spentUsd / this.limitUsd : 0;
    let warning = "";

    if (usageFraction >= this.config.alertThresholdCritical) {
      warning = `CRITICAL: ${(usageFraction * 100).toFixed(0)}% of session budget used ($${this.spentUsd.toFixed(4)} / $${this.limitUsd.toFixed(2)})`;
    } else if (usageFraction >= this.config.alertThresholdWarning) {
      warning = `WARNING: ${(usageFraction * 100).toFixed(0)}% of session budget used ($${this.spentUsd.toFixed(4)} / $${this.limitUsd.toFixed(2)})`;
    }

    return {
      allowed: true,
      remainingUsd: remaining,
      spentUsd: this.spentUsd,
      limitUsd: this.limitUsd,
      warning,
    };
  }

  /** Reset tracker for a new session. */
  reset(limitUsd?: number): void {
    this.spentUsd = 0;
    if (limitUsd !== undefined) {
      this.limitUsd = limitUsd;
    }
  }
}
