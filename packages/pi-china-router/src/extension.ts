/**
 * Pi extension entry point for SilkRoute Chinese LLM routing.
 *
 * Hooks into pi's lifecycle events to:
 * - Auto-classify tasks and select the appropriate tier/model
 * - Register /tier and /models commands
 * - Provide model registry access to other extensions
 *
 * This is the file referenced in package.json's pi.extensions field.
 */

import { classifyTask } from "./classifier.js";
import { ALL_MODELS, MODELS_BY_TIER } from "./models.js";
import { routeTask } from "./router.js";
import { ModelTier } from "./types.js";

/** Current tier state (can be overridden by user via /tier command). */
let currentTierOverride: ModelTier | undefined;
let lastClassificationReason = "";

/**
 * Pi extension registration function.
 *
 * Called by pi when the extension is loaded. Receives the ExtensionAPI
 * which provides hooks, commands, and state access.
 *
 * NOTE: The exact ExtensionAPI shape depends on the pi version.
 * This uses the documented extension interface from pi-mono.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export default function register(pi: any): void {
  // ─── Command: /tier ───────────────────────────────────────────────
  pi.registerCommand?.("tier", {
    description: "Show or set the SilkRoute routing tier (free, standard, premium, auto)",
    execute: async (args: string[]) => {
      const tierArg = args[0]?.toLowerCase();

      if (!tierArg || tierArg === "show") {
        const tier = currentTierOverride ?? "auto";
        const info = currentTierOverride
          ? `Tier locked to: ${currentTierOverride}`
          : `Tier: auto (last: ${lastClassificationReason || "none"})`;
        return { content: info, details: `Current tier: ${tier}` };
      }

      if (tierArg === "auto") {
        currentTierOverride = undefined;
        return { content: "Tier routing set to auto-classify.", details: "Auto mode" };
      }

      const validTiers: Record<string, ModelTier> = {
        free: ModelTier.FREE,
        standard: ModelTier.STANDARD,
        premium: ModelTier.PREMIUM,
      };

      const tier = validTiers[tierArg];
      if (!tier) {
        return {
          content: `Invalid tier '${tierArg}'. Use: free, standard, premium, or auto.`,
          details: "Error",
        };
      }

      currentTierOverride = tier;
      return {
        content: `Tier locked to: ${tier}. Use '/tier auto' to restore auto-classification.`,
        details: `Locked: ${tier}`,
      };
    },
  });

  // ─── Command: /models ─────────────────────────────────────────────
  pi.registerCommand?.("models", {
    description: "Show all 13 SilkRoute Chinese LLM models by tier",
    execute: async () => {
      const lines: string[] = [];

      for (const tier of [ModelTier.FREE, ModelTier.STANDARD, ModelTier.PREMIUM]) {
        const models = MODELS_BY_TIER[tier];
        lines.push(`\n## ${tier.toUpperCase()} TIER`);
        lines.push("| Model | Provider | Input $/M | Output $/M | Context | Capabilities |");
        lines.push("|-------|----------|-----------|------------|---------|-------------|");

        for (const m of models) {
          const caps = m.capabilities.join(", ");
          const ctxK = `${Math.round(m.contextWindow / 1024)}K`;
          const inCost = m.isFree ? "free" : `$${m.inputCostPerM.toFixed(2)}`;
          const outCost = m.isFree ? "free" : `$${m.outputCostPerM.toFixed(2)}`;
          lines.push(`| ${m.name} | ${m.provider} | ${inCost} | ${outCost} | ${ctxK} | ${caps} |`);
        }
      }

      lines.push(`\nTotal: ${ALL_MODELS.size} models`);
      return { content: lines.join("\n"), details: `${ALL_MODELS.size} models` };
    },
  });

  // ─── Hook: input — auto-classify tasks ────────────────────────────
  pi.on?.("input", async (event: { content: string }) => {
    // Only classify if no tier override is set
    if (currentTierOverride) return;

    const result = routeTask(event.content);
    lastClassificationReason = `${result.classification.tier} (${result.classification.reason})`;

    // Set the model on the pi context for the next LLM call
    // The exact method depends on pi's extension API version
    if (pi.setModel) {
      const piModelId = `openrouter:${result.model.modelId}`;
      pi.setModel(piModelId);
    }
  });

  // ─── Hook: model_select — enforce tier routing ────────────────────
  pi.on?.("model_select", async () => {
    if (!currentTierOverride) return;

    // When tier is manually locked, route to the default model for that tier
    const result = routeTask("", undefined, currentTierOverride);
    if (pi.setModel) {
      const piModelId = `openrouter:${result.model.modelId}`;
      pi.setModel(piModelId);
    }
  });
}
