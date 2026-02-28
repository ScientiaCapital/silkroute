"""Deep Agents runtime — wraps create_deep_agent() via the code_writer module.

Delegates to run_code_writer() which handles agent creation, invocation,
and result translation. The sync agent.invoke() call runs in a thread
executor to avoid blocking the async event loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from functools import partial

import structlog

from silkroute.mantis.runtime.interface import AgentResult, RuntimeConfig

log = structlog.get_logger()


class DeepAgentsRuntime:
    """Wraps Deep Agents create_deep_agent() behind the AgentRuntime protocol."""

    @property
    def name(self) -> str:
        return "deepagents"

    async def invoke(self, task: str, config: RuntimeConfig | None = None) -> AgentResult:
        """Run a task using the Deep Agents framework.

        Creates a Code Writer agent via run_code_writer() and executes the
        task in a thread executor (agent.invoke() is synchronous).

        Raises:
            NotImplementedError: If deepagents package is not installed.
        """
        try:
            import deepagents  # noqa: F401
        except ImportError:
            raise NotImplementedError(
                "Deep Agents runtime requires 'deepagents' package. "
                "Install with: pip install 'silkroute[mantis]'"
            ) from None

        cfg = config or RuntimeConfig()

        from silkroute.mantis.agents.code_writer import run_code_writer

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            partial(
                run_code_writer,
                task=task,
                workspace_dir=cfg.workspace_dir,
                model_id=cfg.model_override or "deepseek/deepseek-v3.2",
                recursion_limit=cfg.max_iterations,
            ),
        )

        log.info(
            "deepagents_invoke_complete",
            status=result.status,
            task_preview=task[:80],
        )

        return AgentResult(
            status=result.status,
            output=result.output,
            error=result.error,
            iterations=result.iterations,
            cost_usd=result.cost_usd,
            metadata={"runtime": "deepagents", "model": cfg.model_override, **result.metadata},
        )

    async def stream(
        self, task: str, config: RuntimeConfig | None = None
    ) -> AsyncIterator[str]:
        """Stream output from Deep Agents — batch-then-yield for Phase 1."""
        result = await self.invoke(task, config)
        yield result.output
