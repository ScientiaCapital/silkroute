"""Legacy runtime — wraps the existing SilkRoute ReAct agent loop.

This is the default runtime backend. It delegates to run_agent() from
silkroute.agent.loop, translating the AgentSession result into an
AgentResult for the unified runtime interface.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import structlog

from silkroute.mantis.runtime.interface import AgentResult, RuntimeConfig

log = structlog.get_logger()


class LegacyRuntime:
    """Wraps the existing ReAct loop as an AgentRuntime implementation."""

    @property
    def name(self) -> str:
        return "legacy"

    async def invoke(self, task: str, config: RuntimeConfig | None = None) -> AgentResult:
        """Run a task using the existing ReAct agent loop."""
        from silkroute.agent.loop import run_agent

        cfg = config or RuntimeConfig()

        session = await run_agent(
            task,
            model_override=cfg.model_override,
            tier_override=cfg.tier_override,
            project_id=cfg.project_id,
            max_iterations=cfg.max_iterations,
            budget_limit_usd=cfg.budget_limit_usd,
            workspace_dir=cfg.workspace_dir,
            daemon_mode=True,  # Always daemon mode through runtime API
        )

        # Map AgentSession fields to AgentResult
        last_thought = ""
        if session.iterations:
            last_thought = session.iterations[-1].thought

        return AgentResult(
            status=session.status.value,
            session_id=session.id,
            iterations=session.iteration_count,
            cost_usd=session.total_cost_usd,
            output=last_thought,
            error="" if session.status.value == "completed" else session.status.value,
            metadata={
                "model_id": session.model_id,
                "total_input_tokens": session.total_input_tokens,
                "total_output_tokens": session.total_output_tokens,
            },
        )

    async def stream(self, task: str, config: RuntimeConfig | None = None) -> AsyncIterator[str]:
        """Stream output — legacy runtime doesn't support true streaming.

        Falls back to running the full task and yielding the result.
        """
        result = await self.invoke(task, config)
        yield result.output
