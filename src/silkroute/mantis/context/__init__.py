"""Context management package for SilkRoute Mantis agents.

Provides ContextManager for versioned, token-aware, scope-filtered
inter-step context sharing in supervisor plans.
"""

from __future__ import annotations

from silkroute.mantis.context.manager import ContextManager
from silkroute.mantis.context.models import ContextEntry, ContextScope, ContextSnapshot

__all__ = ["ContextEntry", "ContextManager", "ContextScope", "ContextSnapshot"]
