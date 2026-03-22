"""ResearchTarget protocol — what the experiment engine optimizes."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from silkroute.autoresearch.metrics import Metrics


@runtime_checkable
class ResearchTarget(Protocol):
    """Protocol for research targets.

    Each target defines:
    - What files the agent can edit (allowed_paths)
    - How to evaluate the current state (evaluate)
    - How to build context for the LLM (build_context)
    """

    name: str
    allowed_paths: list[str]
    max_diff_lines: int

    async def evaluate(self) -> Metrics:
        """Run the target's evaluation and return metrics."""
        ...

    async def build_context(self, recent_entries: list[dict]) -> str:
        """Build context string for the LLM researcher.

        Args:
            recent_entries: Last N ledger entries for experiment history.

        Returns:
            Context string with test output, coverage, and history.
        """
        ...
