"""Runtime registry — factory for AgentRuntime instances.

Selects the runtime backend based on SILKROUTE_RUNTIME env var:
- "legacy" (default): uses the existing ReAct loop
- "deepagents": uses Deep Agents framework (Phase 1)
"""

from __future__ import annotations

import os

import structlog

from silkroute.mantis.runtime.interface import AgentRuntime, RuntimeType

log = structlog.get_logger()

# Cache: avoid re-instantiating on every call
_cached_runtime: AgentRuntime | None = None
_cached_type: str | None = None


def get_runtime(runtime_type: str | None = None) -> AgentRuntime:
    """Get or create the active AgentRuntime.

    Args:
        runtime_type: Override the runtime type. If None, reads from
            SILKROUTE_RUNTIME env var (default: "legacy").

    Returns:
        An AgentRuntime instance.

    Raises:
        ValueError: If the runtime type is unknown.
    """
    global _cached_runtime, _cached_type  # noqa: PLW0603

    rt = runtime_type or os.environ.get("SILKROUTE_RUNTIME", RuntimeType.LEGACY)

    # Return cached instance if type matches
    if _cached_runtime is not None and _cached_type == rt:
        return _cached_runtime

    if rt == RuntimeType.LEGACY:
        from silkroute.mantis.runtime.legacy import LegacyRuntime

        _cached_runtime = LegacyRuntime()
    elif rt == RuntimeType.DEEP_AGENTS:
        from silkroute.mantis.runtime.deepagents import DeepAgentsRuntime

        _cached_runtime = DeepAgentsRuntime()
    else:
        raise ValueError(
            f"Unknown runtime type: {rt!r}. "
            f"Valid options: {RuntimeType.LEGACY!r}, {RuntimeType.DEEP_AGENTS!r}"
        )

    _cached_type = rt
    log.info("runtime_selected", runtime=rt)
    return _cached_runtime


def reset_runtime() -> None:
    """Clear the cached runtime instance (for testing)."""
    global _cached_runtime, _cached_type  # noqa: PLW0603
    _cached_runtime = None
    _cached_type = None
