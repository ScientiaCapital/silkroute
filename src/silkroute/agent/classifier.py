"""Keyword-based task classification for tier routing.

No LLM call needed — fast, free, deterministic. Maps natural-language
task descriptions to a ModelTier + required capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from silkroute.config.settings import ModelTier
from silkroute.providers.models import Capability


@dataclass
class TaskClassification:
    """Result of classifying a task string."""

    tier: ModelTier
    capabilities: list[Capability] = field(default_factory=list)
    confidence: float = 0.5
    reason: str = ""


# Multi-word patterns checked first to avoid false positives
_PREMIUM_TRIGGERS = [
    "security review", "security audit", "complex debug", "deep debug",
    "architect", "migration plan", "performance profil", "vulnerability",
    "codebase refactor", "system design",
]

_STANDARD_TRIGGERS = [
    "review", "refactor", "implement", "fix bug", "write test",
    "add feature", "debug", "optimize", "analyze", "create",
    "build", "develop", "integrate", "update", "modify",
]

_FREE_TRIGGERS = [
    "summarize", "format", "lint", "label", "triage",
    "list", "describe", "explain", "translate", "count",
    "rename", "typo", "comment", "log", "echo",
]

_CAPABILITY_KEYWORDS: dict[str, Capability] = {
    "code": Capability.CODING,
    "implement": Capability.CODING,
    "write": Capability.CODING,
    "build": Capability.CODING,
    "develop": Capability.CODING,
    "script": Capability.CODING,
    "function": Capability.CODING,
    "class": Capability.CODING,
    "refactor": Capability.CODING,
    "fix": Capability.CODING,
    "reason": Capability.REASONING,
    "analyze": Capability.REASONING,
    "debug": Capability.REASONING,
    "explain": Capability.REASONING,
    "why": Capability.REASONING,
    "compare": Capability.REASONING,
    "tool": Capability.TOOL_CALLING,
    "run": Capability.TOOL_CALLING,
    "exec": Capability.TOOL_CALLING,
    "shell": Capability.TOOL_CALLING,
    "command": Capability.TOOL_CALLING,
    "file": Capability.TOOL_CALLING,
    "read": Capability.TOOL_CALLING,
    "agent": Capability.AGENTIC,
    "automat": Capability.AGENTIC,
    "workflow": Capability.AGENTIC,
    "pipeline": Capability.AGENTIC,
    "math": Capability.MATH,
    "calcul": Capability.MATH,
    "creative": Capability.CREATIVE,
    "story": Capability.CREATIVE,
    "generate": Capability.CREATIVE,
}


def classify_task(task: str) -> TaskClassification:
    """Classify a task string into a tier and required capabilities.

    Priority: PREMIUM triggers > STANDARD triggers > FREE triggers > default STANDARD.
    """
    lower = task.lower()

    # Determine tier (check premium first, then free, then standard)
    tier = ModelTier.STANDARD
    reason = "default routing"
    confidence = 0.4

    for trigger in _PREMIUM_TRIGGERS:
        if trigger in lower:
            tier = ModelTier.PREMIUM
            reason = f"matched premium trigger: '{trigger}'"
            confidence = 0.8
            break

    if tier == ModelTier.STANDARD:
        # Check free before standard — standard is the default fallback
        for trigger in _FREE_TRIGGERS:
            if trigger in lower:
                tier = ModelTier.FREE
                reason = f"matched free trigger: '{trigger}'"
                confidence = 0.7
                break

    if tier == ModelTier.STANDARD and confidence < 0.5:
        for trigger in _STANDARD_TRIGGERS:
            if trigger in lower:
                reason = f"matched standard trigger: '{trigger}'"
                confidence = 0.7
                break

    # Detect capabilities
    capabilities: list[Capability] = []
    seen: set[Capability] = set()
    for keyword, cap in _CAPABILITY_KEYWORDS.items():
        if keyword in lower and cap not in seen:
            capabilities.append(cap)
            seen.add(cap)

    # Default capabilities if none detected
    if not capabilities:
        capabilities = [Capability.CODING, Capability.TOOL_CALLING]

    return TaskClassification(
        tier=tier,
        capabilities=capabilities,
        confidence=confidence,
        reason=reason,
    )
