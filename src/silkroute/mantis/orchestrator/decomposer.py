"""Task decomposition — split compound tasks into sub-tasks.

KeywordDecomposer uses simple string splitting on compound markers
(" and then ", " and ", numbered lists) to break tasks apart. Each
sub-task is classified using the existing classify_task() function
from agent/classifier.py, keeping decomposition deterministic and free.
"""

from __future__ import annotations

import re
from typing import Protocol

from silkroute.agent.classifier import classify_task
from silkroute.mantis.orchestrator.models import OrchestrationPlan, SubTask
from silkroute.mantis.runtime.interface import RuntimeConfig


class TaskDecomposer(Protocol):
    """Protocol for task decomposition strategies."""

    def decompose(self, task: str, config: RuntimeConfig | None = None) -> OrchestrationPlan:
        """Split a task into an OrchestrationPlan with sub-tasks."""
        ...


# Compound markers, ordered from most specific to least
_COMPOUND_MARKERS = [
    " and then ",
    " then ",
    "; then ",
    "; ",
]

# Pattern for numbered lists: "1. foo 2. bar 3. baz" or "1) foo 2) bar"
_NUMBERED_RE = re.compile(r"(?:^|\s)(\d+)[.)]\s+", re.MULTILINE)


def _split_compound(task: str) -> list[str]:
    """Split a compound task into sub-task descriptions.

    Tries numbered lists first, then compound markers, then " and ".
    Returns a list of at least one non-empty string.
    """
    # Try numbered list first
    parts = _NUMBERED_RE.split(task)
    if len(parts) > 2:
        # parts = ['preamble', '1', 'desc1', '2', 'desc2', ...]
        descriptions = [parts[i].strip() for i in range(2, len(parts), 2)]
        descriptions = [d for d in descriptions if d]
        if len(descriptions) >= 2:
            return descriptions

    # Try compound markers
    for marker in _COMPOUND_MARKERS:
        if marker in task.lower():
            # Case-insensitive split
            pattern = re.compile(re.escape(marker), re.IGNORECASE)
            parts_list = pattern.split(task)
            parts_list = [p.strip() for p in parts_list if p.strip()]
            if len(parts_list) >= 2:
                return parts_list

    # Try " and " as last resort (only if it splits into exactly 2-3 parts)
    if " and " in task.lower():
        pattern = re.compile(r"\s+and\s+", re.IGNORECASE)
        parts_list = pattern.split(task)
        parts_list = [p.strip() for p in parts_list if p.strip()]
        if 2 <= len(parts_list) <= 3:
            return parts_list

    # Single task — no decomposition
    return [task.strip()]


class KeywordDecomposer:
    """Keyword-based task decomposer.

    Splits compound tasks using textual markers and classifies each
    sub-task using the existing tier classifier. Budget is distributed
    proportionally by tier weight.
    """

    def decompose(self, task: str, config: RuntimeConfig | None = None) -> OrchestrationPlan:
        cfg = config or RuntimeConfig()
        descriptions = _split_compound(task)

        sub_tasks: list[SubTask] = []
        prev_id: str | None = None

        for i, desc in enumerate(descriptions):
            classification = classify_task(desc)

            st = SubTask(
                parent_task=task,
                description=desc,
                runtime_type=cfg.runtime_type,
                tier_hint=classification.tier.value,
                max_iterations=cfg.max_iterations,
                priority=len(descriptions) - i,  # Earlier tasks get higher priority
                metadata={"classification_reason": classification.reason},
            )

            # Sequential dependency for " and then " / " then " style
            if prev_id is not None and any(
                m in task.lower() for m in (" and then ", " then ", "; then ")
            ):
                st.depends_on = [prev_id]

            sub_tasks.append(st)
            prev_id = st.id

        return OrchestrationPlan(
            parent_task=task,
            sub_tasks=sub_tasks,
            strategy="parallel_stages" if len(sub_tasks) > 1 else "single",
            total_budget_usd=cfg.budget_limit_usd,
        )


class SingleTaskDecomposer:
    """Pass-through decomposer for simple (non-compound) tasks.

    Always creates a plan with exactly one sub-task.
    """

    def decompose(self, task: str, config: RuntimeConfig | None = None) -> OrchestrationPlan:
        cfg = config or RuntimeConfig()
        classification = classify_task(task)

        st = SubTask(
            parent_task=task,
            description=task,
            runtime_type=cfg.runtime_type,
            tier_hint=classification.tier.value,
            budget_usd=cfg.budget_limit_usd,
            max_iterations=cfg.max_iterations,
        )

        return OrchestrationPlan(
            parent_task=task,
            sub_tasks=[st],
            strategy="single",
            total_budget_usd=cfg.budget_limit_usd,
        )
