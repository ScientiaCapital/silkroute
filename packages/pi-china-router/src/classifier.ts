/**
 * Keyword-based task classification for tier routing.
 *
 * No LLM call needed — fast, free, deterministic. Maps natural-language
 * task descriptions to a ModelTier + required capabilities.
 *
 * Ported from: src/silkroute/agent/classifier.py
 */

import { Capability, ModelTier, TaskClassification } from "./types.js";

// Multi-word patterns checked first to avoid false positives
const PREMIUM_TRIGGERS = [
  "security review",
  "security audit",
  "complex debug",
  "deep debug",
  "architect",
  "migration plan",
  "performance profil",
  "vulnerability",
  "codebase refactor",
  "system design",
];

const STANDARD_TRIGGERS = [
  "review",
  "refactor",
  "implement",
  "fix bug",
  "write test",
  "add feature",
  "debug",
  "optimize",
  "analyze",
  "create",
  "build",
  "develop",
  "integrate",
  "update",
  "modify",
];

const FREE_TRIGGERS = [
  "summarize",
  "format",
  "lint",
  "label",
  "triage",
  "list",
  "describe",
  "explain",
  "translate",
  "count",
  "rename",
  "typo",
  "comment",
  "log",
  "echo",
];

const CAPABILITY_KEYWORDS: ReadonlyMap<string, Capability> = new Map([
  ["code", Capability.CODING],
  ["implement", Capability.CODING],
  ["write", Capability.CODING],
  ["build", Capability.CODING],
  ["develop", Capability.CODING],
  ["script", Capability.CODING],
  ["function", Capability.CODING],
  ["class", Capability.CODING],
  ["refactor", Capability.CODING],
  ["fix", Capability.CODING],
  ["reason", Capability.REASONING],
  ["analyze", Capability.REASONING],
  ["debug", Capability.REASONING],
  ["explain", Capability.REASONING],
  ["why", Capability.REASONING],
  ["compare", Capability.REASONING],
  ["tool", Capability.TOOL_CALLING],
  ["run", Capability.TOOL_CALLING],
  ["exec", Capability.TOOL_CALLING],
  ["shell", Capability.TOOL_CALLING],
  ["command", Capability.TOOL_CALLING],
  ["file", Capability.TOOL_CALLING],
  ["read", Capability.TOOL_CALLING],
  ["agent", Capability.AGENTIC],
  ["automat", Capability.AGENTIC],
  ["workflow", Capability.AGENTIC],
  ["pipeline", Capability.AGENTIC],
  ["math", Capability.MATH],
  ["calcul", Capability.MATH],
  ["creative", Capability.CREATIVE],
  ["story", Capability.CREATIVE],
  ["generate", Capability.CREATIVE],
]);

/**
 * Classify a task string into a tier and required capabilities.
 *
 * Priority: PREMIUM triggers > FREE triggers > STANDARD triggers > default STANDARD.
 */
export function classifyTask(task: string): TaskClassification {
  const lower = task.toLowerCase();

  // Determine tier (check premium first, then free, then standard)
  let tier = ModelTier.STANDARD;
  let reason = "default routing";
  let confidence = 0.4;

  for (const trigger of PREMIUM_TRIGGERS) {
    if (lower.includes(trigger)) {
      tier = ModelTier.PREMIUM;
      reason = `matched premium trigger: '${trigger}'`;
      confidence = 0.8;
      break;
    }
  }

  if (tier === ModelTier.STANDARD) {
    // Check free before standard — standard is the default fallback
    for (const trigger of FREE_TRIGGERS) {
      if (lower.includes(trigger)) {
        tier = ModelTier.FREE;
        reason = `matched free trigger: '${trigger}'`;
        confidence = 0.7;
        break;
      }
    }
  }

  if (tier === ModelTier.STANDARD && confidence < 0.5) {
    for (const trigger of STANDARD_TRIGGERS) {
      if (lower.includes(trigger)) {
        reason = `matched standard trigger: '${trigger}'`;
        confidence = 0.7;
        break;
      }
    }
  }

  // Detect capabilities
  const capabilities: Capability[] = [];
  const seen = new Set<Capability>();
  for (const [keyword, cap] of CAPABILITY_KEYWORDS) {
    if (lower.includes(keyword) && !seen.has(cap)) {
      capabilities.push(cap);
      seen.add(cap);
    }
  }

  // Default capabilities if none detected
  if (capabilities.length === 0) {
    capabilities.push(Capability.CODING, Capability.TOOL_CALLING);
  }

  return { tier, capabilities, confidence, reason };
}
