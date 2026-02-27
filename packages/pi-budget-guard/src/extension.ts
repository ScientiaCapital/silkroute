/**
 * Pi extension entry point for SilkRoute budget governance.
 *
 * Hooks into pi's lifecycle events to:
 * - Track costs per turn using pi-ai's built-in token tracking
 * - Enforce per-session budget limits with warning thresholds
 * - Register /budget command
 */

import { CostTracker } from "./cost-tracker.js";
import { DEFAULT_BUDGET_CONFIG } from "./types.js";

/**
 * Pi extension registration function.
 *
 * Called by pi when the extension is loaded.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export default function register(pi: any): void {
  const tracker = new CostTracker(
    DEFAULT_BUDGET_CONFIG.dailyMaxUsd,
    DEFAULT_BUDGET_CONFIG,
  );

  // ─── Hook: session_start — reset budget tracker ───────────────────
  pi.on?.("session_start", async () => {
    // Load budget limit from environment or settings
    const envLimit = process.env.SILKROUTE_BUDGET_DAILY_MAX_USD;
    const limit = envLimit ? parseFloat(envLimit) : DEFAULT_BUDGET_CONFIG.dailyMaxUsd;
    tracker.reset(limit);
  });

  // ─── Hook: turn_end — record cost and check budget ────────────────
  pi.on?.("turn_end", async (event: { usage?: { cost?: { total?: number }; input?: number; output?: number } }) => {
    const cost = event.usage?.cost?.total ?? 0;
    if (cost > 0) {
      tracker.recordCost(cost);
    }

    // Check budget after recording
    const currentModel = pi.getModel?.()?.id ?? "deepseek/deepseek-v3.2";
    const check = tracker.checkBudget(currentModel);

    if (!check.allowed) {
      pi.ui?.notify?.("Budget exhausted. Session will end.", "error");
      pi.abort?.();
      return;
    }

    if (check.warning) {
      pi.ui?.notify?.(check.warning, "warning");
    }
  });

  // ─── Command: /budget ─────────────────────────────────────────────
  pi.registerCommand?.("budget", {
    description: "Show session budget status — spend, remaining, limits",
    execute: async () => {
      const spent = tracker.totalSpent;
      const remaining = tracker.remaining;
      const pct = tracker.totalSpent > 0
        ? ((spent / (spent + remaining)) * 100).toFixed(1)
        : "0.0";

      const lines = [
        "## SilkRoute Budget Status",
        "",
        `| Metric | Value |`,
        `|--------|-------|`,
        `| Spent | $${spent.toFixed(4)} |`,
        `| Remaining | $${remaining.toFixed(4)} |`,
        `| Usage | ${pct}% |`,
      ];

      return { content: lines.join("\n"), details: `$${spent.toFixed(4)} spent` };
    },
  });
}
