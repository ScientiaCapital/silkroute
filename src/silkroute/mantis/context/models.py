"""Context management data models.

ContextEntry, ContextScope, and ContextSnapshot support the ContextManager's
versioned, token-aware, scope-filtered context store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ContextScope(StrEnum):
    STEP = "step"
    PLAN = "plan"
    SESSION = "session"


@dataclass
class ContextEntry:
    """A single versioned context entry."""

    key: str
    value: Any
    scope: ContextScope
    source: str = ""  # e.g. "step_1", "user", "system"
    token_estimate: int = 0
    version: int = 1


@dataclass
class ContextSnapshot:
    """Serializable snapshot for checkpoint persistence."""

    entries: dict[str, ContextEntry] = field(default_factory=dict)
    total_tokens: int = 0
    version: int = 1
