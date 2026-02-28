"""Agent runtime abstraction — swap between execution backends.

The runtime layer provides a unified interface for running agent tasks,
regardless of the underlying framework (legacy ReAct loop, Deep Agents,
or LangGraph). Controlled by the SILKROUTE_RUNTIME environment variable.

Usage::

    from silkroute.mantis.runtime import get_runtime

    runtime = get_runtime()
    result = await runtime.invoke("Fix the failing test in test_auth.py")
"""

from silkroute.mantis.runtime.interface import (
    AgentResult,
    AgentRuntime,
    RuntimeConfig,
)
from silkroute.mantis.runtime.registry import get_runtime

__all__ = [
    "AgentResult",
    "AgentRuntime",
    "RuntimeConfig",
    "get_runtime",
]
