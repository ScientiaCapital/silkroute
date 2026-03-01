"""Skills framework for SilkRoute Mantis agents.

Provides SkillSpec, SkillContext, SkillResult, SkillCategory, and SkillRegistry
as the higher-level abstraction layer on top of the agent's ToolRegistry.
"""

from __future__ import annotations

from silkroute.mantis.skills.models import SkillCategory, SkillContext, SkillResult, SkillSpec
from silkroute.mantis.skills.registry import SkillRegistry

__all__ = ["SkillCategory", "SkillContext", "SkillRegistry", "SkillResult", "SkillSpec"]
