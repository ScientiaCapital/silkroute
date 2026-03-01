"""Skill catalog API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from silkroute.api.models import SkillResponse
from silkroute.mantis.skills import SkillCategory, SkillRegistry
from silkroute.mantis.skills.builtin import register_builtin_skills

router = APIRouter(prefix="/skills", tags=["skills"])


def _get_registry() -> SkillRegistry:
    """Get a populated skill registry."""
    registry = SkillRegistry()
    register_builtin_skills(registry)
    return registry


@router.get("", response_model=list[SkillResponse])
async def list_skills(category: str | None = None) -> list[SkillResponse]:
    """List all available skills, optionally filtered by category."""
    registry = _get_registry()

    cat_filter: SkillCategory | None = None
    if category is not None:
        try:
            cat_filter = SkillCategory(category)
        except ValueError:
            valid = [c.value for c in SkillCategory]
            raise HTTPException(
                status_code=422,
                detail=f"Invalid category '{category}'. Valid values: {valid}",
            ) from None

    skills = registry.list_skills(category=cat_filter)
    return [
        SkillResponse(
            name=s.name,
            description=s.description,
            category=s.category.value,
            parameters=s.parameters,
            is_llm_native=s.is_llm_native,
            model_hint=s.model_hint,
            max_budget_usd=s.max_budget_usd,
            version=s.version,
            required_tools=s.required_tools,
        )
        for s in skills
    ]


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(skill_id: str) -> SkillResponse:
    """Get details for a specific skill."""
    registry = _get_registry()
    skill = registry.get(skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")
    return SkillResponse(
        name=skill.name,
        description=skill.description,
        category=skill.category.value,
        parameters=skill.parameters,
        is_llm_native=skill.is_llm_native,
        model_hint=skill.model_hint,
        max_budget_usd=skill.max_budget_usd,
        version=skill.version,
        required_tools=skill.required_tools,
    )
