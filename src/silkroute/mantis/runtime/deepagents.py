"""Deep Agents runtime — wraps create_deep_agent() from the deepagents library.

This is a STUB for Phase 1. It validates that the abstraction layer works
but raises NotImplementedError until deepagents is added as a dependency.

The runtime will be fully implemented in Phase 1 when we add:
- deepagents==0.4.1 (exact pin)
- langchain-openai>=0.3.0
- langgraph>=0.2.0
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import structlog

from silkroute.mantis.runtime.interface import AgentResult, RuntimeConfig

log = structlog.get_logger()


class DeepAgentsRuntime:
    """Wraps Deep Agents create_deep_agent() — STUB until Phase 1."""

    @property
    def name(self) -> str:
        return "deepagents"

    async def invoke(self, task: str, config: RuntimeConfig | None = None) -> AgentResult:
        """Run a task using Deep Agents framework.

        Raises NotImplementedError until Phase 1 adds the deepagents dependency.
        """
        try:
            import deepagents  # noqa: F401
        except ImportError:
            raise NotImplementedError(
                "Deep Agents runtime requires 'deepagents' package. "
                "Install with: pip install deepagents==0.4.1. "
                "This will be available in Phase 1."
            ) from None

        # Phase 1 implementation will go here:
        # 1. Create agent via create_deep_agent()
        # 2. Configure tools, skills, model
        # 3. Invoke and translate result
        raise NotImplementedError("Deep Agents runtime is a Phase 1 feature")

    async def stream(self, task: str, config: RuntimeConfig | None = None) -> AsyncIterator[str]:
        """Stream output from Deep Agents — stub."""
        raise NotImplementedError("Deep Agents streaming is a Phase 1 feature")
        yield  # pragma: no cover — makes this a generator
