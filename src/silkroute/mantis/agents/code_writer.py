"""Code Writer — first Mantis Deep Agent.

Uses create_deep_agent() with:
- OpenRouter-routed Chinese LLM (default: Qwen3 Coder)
- LocalShellBackend for filesystem + shell access
- Workspace isolation via root_dir

The agent is a LangGraph CompiledStateGraph — invoke() is synchronous,
so callers in async contexts should use asyncio.to_thread or run_in_executor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

log = structlog.get_logger()

_CODE_WRITER_PROMPT = """\
You are a senior Python developer working on the SilkRoute project.

Guidelines:
- Write clean, well-structured Python 3.12+ code
- Follow existing project conventions (ruff, type hints, structlog)
- Run tests after making changes
- Prefer editing existing files over creating new ones
- Keep changes minimal and focused on the task
"""


@dataclass
class CodeWriterResult:
    """Result from a Code Writer agent execution."""

    status: str  # "completed" | "failed" | "import_error"
    output: str = ""
    error: str = ""
    iterations: int = 0
    cost_usd: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


def create_code_writer(
    workspace_dir: str = ".",
    model_id: str = "qwen/qwen3-coder",
    api_key: str | None = None,
    system_prompt: str | None = None,
) -> CompiledStateGraph:
    """Create a Code Writer Deep Agent.

    Args:
        workspace_dir: Root directory for filesystem and shell access.
        model_id: OpenRouter model identifier.
        api_key: Explicit OpenRouter API key (falls back to env vars).
        system_prompt: Override the default system prompt.

    Returns:
        A LangGraph CompiledStateGraph ready for invoke()/stream().

    Raises:
        ImportError: If deepagents is not installed.
    """
    from deepagents import create_deep_agent
    from deepagents.backends import LocalShellBackend

    from silkroute.providers.openrouter import create_openrouter_model

    model = create_openrouter_model(model_id=model_id, api_key=api_key)
    backend = LocalShellBackend(root_dir=workspace_dir)

    agent = create_deep_agent(
        model=model,
        backend=backend,
        name="code-writer",
        system_prompt=system_prompt or _CODE_WRITER_PROMPT,
    )

    log.info(
        "code_writer_created",
        model=model_id,
        workspace=workspace_dir,
    )
    return agent


def run_code_writer(
    task: str,
    workspace_dir: str = ".",
    model_id: str = "qwen/qwen3-coder",
    api_key: str | None = None,
    recursion_limit: int = 50,
) -> CodeWriterResult:
    """Create and run a Code Writer agent synchronously.

    This is a convenience function that handles agent creation, invocation,
    and result translation in one call.

    Args:
        task: The coding task to perform.
        workspace_dir: Root directory for filesystem and shell access.
        model_id: OpenRouter model identifier.
        api_key: Explicit OpenRouter API key.
        recursion_limit: Max LangGraph recursion depth (controls iterations).

    Returns:
        CodeWriterResult with status, output, and metadata.
    """
    try:
        agent = create_code_writer(
            workspace_dir=workspace_dir,
            model_id=model_id,
            api_key=api_key,
        )
    except ImportError:
        return CodeWriterResult(
            status="import_error",
            error="deepagents package not installed. Install with: pip install 'silkroute[mantis]'",
        )

    try:
        from langchain_core.messages import HumanMessage

        result = agent.invoke(
            {"messages": [HumanMessage(content=task)]},
            config={"recursion_limit": recursion_limit},
        )

        # Extract output from the last AI message
        messages = result.get("messages", [])
        output = ""
        if messages:
            last_msg = messages[-1]
            output = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

        log.info("code_writer_completed", task_preview=task[:80])
        return CodeWriterResult(
            status="completed",
            output=output,
            metadata={"runtime": "deepagents", "model": model_id},
        )
    except Exception as exc:
        log.error("code_writer_failed", error=str(exc))
        return CodeWriterResult(
            status="failed",
            error=str(exc),
            metadata={"runtime": "deepagents", "model": model_id},
        )
