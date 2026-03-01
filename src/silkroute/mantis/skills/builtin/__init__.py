"""Built-in skill registration for the SilkRoute skills framework."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from silkroute.mantis.skills.registry import SkillRegistry


def register_builtin_skills(registry: SkillRegistry) -> None:
    """Register all built-in skills with the registry."""
    from silkroute.mantis.skills.builtin.docs_skill import docs_lookup_skill
    from silkroute.mantis.skills.builtin.http_skill import http_request_skill
    from silkroute.mantis.skills.builtin.llm_skill import code_review_skill, summarize_skill
    from silkroute.mantis.skills.builtin.search_skill import search_grep_skill

    for skill in [
        http_request_skill,
        search_grep_skill,
        docs_lookup_skill,
        code_review_skill,
        summarize_skill,
    ]:
        registry.register(skill)
