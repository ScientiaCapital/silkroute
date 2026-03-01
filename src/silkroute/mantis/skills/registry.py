"""SkillRegistry — register, list, execute, and mount skills.

Skills are higher-level abstractions on top of the agent's ToolRegistry.
The mount() method bridges all registered skills into a ToolRegistry so
agents see skills as regular tools.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from silkroute.mantis.skills.models import SkillCategory, SkillContext, SkillResult, SkillSpec

if TYPE_CHECKING:
    from silkroute.agent.tools import ToolRegistry

log = structlog.get_logger()


class SkillRegistry:
    """Registry for higher-level agent skills.

    Skills extend the basic ToolRegistry with structured metadata,
    budget awareness, and LLM-native execution patterns.
    """

    def __init__(self) -> None:
        self._skills: dict[str, SkillSpec] = {}

    def register(self, skill: SkillSpec) -> None:
        """Add a skill to the registry."""
        self._skills[skill.name] = skill
        log.debug("skill_registered", name=skill.name, category=skill.category)

    def get(self, name: str) -> SkillSpec | None:
        """Look up a skill by name. Returns None if not found."""
        return self._skills.get(name)

    def list_skills(self, category: SkillCategory | None = None) -> list[SkillSpec]:
        """Return all registered skills, optionally filtered by category."""
        skills = list(self._skills.values())
        if category is not None:
            skills = [s for s in skills if s.category == category]
        return skills

    async def execute(self, name: str, ctx: SkillContext, **kwargs: object) -> SkillResult:
        """Execute a named skill, injecting ctx as _skill_ctx kwarg.

        Returns a SkillResult. On error (missing skill or handler exception),
        returns a failure result rather than raising. Persists execution record
        fire-and-forget if ctx.db_pool is available.
        """
        import time

        skill = self._skills.get(name)
        if skill is None:
            available = ", ".join(self._skills)
            return SkillResult(
                skill_name=name,
                success=False,
                error=f"Unknown skill '{name}'. Available: {available}",
            )

        t0 = time.monotonic()
        try:
            output = await skill.handler(_skill_ctx=ctx, **kwargs)
            result = SkillResult(skill_name=name, success=True, output=output)
        except Exception as e:
            log.error("skill_execution_error", skill=name, error=str(e))
            result = SkillResult(skill_name=name, success=False, error=str(e))

        duration_ms = int((time.monotonic() - t0) * 1000)

        # Fire-and-forget persistence
        if ctx.db_pool is not None:
            try:
                from silkroute.db.repositories.skill_executions import insert_skill_execution

                await insert_skill_execution(
                    ctx.db_pool,
                    skill_name=name,
                    session_id=ctx.session_id,
                    project_id=ctx.project_id,
                    success=result.success,
                    cost_usd=result.cost_usd,
                    duration_ms=duration_ms,
                    output_text=result.output,
                    error_message=result.error,
                )
            except Exception as exc:
                log.warning("skill_execution_persist_failed", skill=name, error=str(exc))

        return result

    def mount(self, tool_registry: ToolRegistry, ctx: SkillContext) -> None:
        """Bridge all skills into a ToolRegistry as regular tools.

        For each skill, wraps its handler to inject _skill_ctx=ctx so agents
        see skills as ordinary ToolSpec entries.
        """
        from silkroute.agent.tools import ToolSpec

        for skill in self._skills.values():
            # Capture skill in closure
            _skill = skill

            async def _wrapped_handler(
                _s: SkillSpec = _skill, _c: SkillContext = ctx, **kw: object
            ) -> str:
                try:
                    return await _s.handler(_skill_ctx=_c, **kw)
                except Exception as e:
                    log.error("mounted_skill_error", skill=_s.name, error=str(e))
                    return f"Error in skill '{_s.name}': {e}"

            tool_registry.register(ToolSpec(
                name=skill.name,
                description=skill.description,
                parameters=skill.parameters,
                handler=_wrapped_handler,
            ))
            log.debug("skill_mounted", name=skill.name)
