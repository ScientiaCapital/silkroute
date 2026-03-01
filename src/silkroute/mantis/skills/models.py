"""Skills framework data models.

Defines SkillSpec, SkillContext, SkillResult, and SkillCategory for the
higher-level skill abstraction layer on top of the agent's ToolRegistry.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SkillCategory(StrEnum):
    CODE = "code"
    WEB = "web"
    SEARCH = "search"
    DOCS = "docs"
    GIT = "git"
    SYSTEM = "system"
    LLM_NATIVE = "llm_native"


# Type alias for skill handler signature
SkillHandler = Callable[..., Awaitable[str]]


@dataclass
class SkillContext:
    """Runtime context injected into skill handlers via _skill_ctx kwarg."""

    tool_registry: Any = None  # ToolRegistry (avoid circular import)
    workspace_dir: str = "."
    budget_remaining_usd: float = 1.0
    _llm_factory: Callable | None = None
    db_pool: Any = None  # asyncpg.Pool (avoid import)
    session_id: str = ""
    project_id: str = "default"

    def get_llm(self, model_id: str | None = None) -> object:
        """Get LLM client. Raises RuntimeError if no factory configured."""
        if self._llm_factory is None:
            raise RuntimeError("No LLM factory configured in SkillContext")
        return self._llm_factory(model_id) if model_id else self._llm_factory()


@dataclass
class SkillSpec:
    """Definition of a higher-level skill the agent can use."""

    name: str
    description: str
    category: SkillCategory
    parameters: dict[str, Any]  # JSON Schema
    handler: SkillHandler
    required_tools: list[str] = field(default_factory=list)
    is_llm_native: bool = False
    system_prompt: str = ""
    model_hint: str = ""
    max_budget_usd: float = 0.50
    version: str = "0.1.0"


@dataclass
class SkillResult:
    """Result from a skill execution."""

    skill_name: str
    success: bool
    output: str = ""
    error: str = ""
    cost_usd: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
