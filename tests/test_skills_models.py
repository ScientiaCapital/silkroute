"""Tests for mantis/skills/models.py — SkillSpec, SkillContext, SkillResult, SkillCategory."""

from __future__ import annotations

import pytest

from silkroute.mantis.skills.models import (
    SkillCategory,
    SkillContext,
    SkillResult,
    SkillSpec,
)


class TestSkillCategory:
    """SkillCategory enum values."""

    def test_all_categories_present(self) -> None:
        assert SkillCategory.CODE == "code"
        assert SkillCategory.WEB == "web"
        assert SkillCategory.SEARCH == "search"
        assert SkillCategory.DOCS == "docs"
        assert SkillCategory.GIT == "git"
        assert SkillCategory.SYSTEM == "system"
        assert SkillCategory.LLM_NATIVE == "llm_native"

    def test_from_string(self) -> None:
        assert SkillCategory("code") == SkillCategory.CODE
        assert SkillCategory("llm_native") == SkillCategory.LLM_NATIVE

    def test_str_behaviour(self) -> None:
        # StrEnum members compare equal to their string values
        assert SkillCategory.WEB == "web"


class TestSkillSpec:
    """SkillSpec creation and defaults."""

    def _make_handler(self) -> object:
        async def _h(**kwargs: object) -> str:
            return "ok"

        return _h

    def test_required_fields(self) -> None:
        handler = self._make_handler()
        spec = SkillSpec(
            name="test_skill",
            description="A test skill",
            category=SkillCategory.SEARCH,
            parameters={"type": "object", "properties": {}},
            handler=handler,  # type: ignore[arg-type]
        )
        assert spec.name == "test_skill"
        assert spec.category == SkillCategory.SEARCH

    def test_defaults(self) -> None:
        handler = self._make_handler()
        spec = SkillSpec(
            name="x",
            description="desc",
            category=SkillCategory.CODE,
            parameters={},
            handler=handler,  # type: ignore[arg-type]
        )
        assert spec.required_tools == []
        assert spec.is_llm_native is False
        assert spec.system_prompt == ""
        assert spec.model_hint == ""
        assert spec.max_budget_usd == 0.50
        assert spec.version == "0.1.0"

    def test_all_fields(self) -> None:
        handler = self._make_handler()
        spec = SkillSpec(
            name="full_skill",
            description="Full",
            category=SkillCategory.LLM_NATIVE,
            parameters={"type": "object"},
            handler=handler,  # type: ignore[arg-type]
            required_tools=["shell_exec"],
            is_llm_native=True,
            system_prompt="Be helpful.",
            model_hint="deepseek/deepseek-r1-0528:free",
            max_budget_usd=1.00,
            version="0.2.0",
        )
        assert spec.required_tools == ["shell_exec"]
        assert spec.is_llm_native is True
        assert spec.system_prompt == "Be helpful."
        assert spec.model_hint == "deepseek/deepseek-r1-0528:free"
        assert spec.max_budget_usd == 1.00
        assert spec.version == "0.2.0"


class TestSkillContext:
    """SkillContext defaults and LLM factory behavior."""

    def test_defaults(self) -> None:
        ctx = SkillContext()
        assert ctx.tool_registry is None
        assert ctx.workspace_dir == "."
        assert ctx.budget_remaining_usd == 1.0
        assert ctx._llm_factory is None

    def test_get_llm_raises_without_factory(self) -> None:
        ctx = SkillContext()
        with pytest.raises(RuntimeError, match="No LLM factory configured"):
            ctx.get_llm()

    def test_get_llm_with_factory_no_model(self) -> None:
        sentinel = object()
        ctx = SkillContext(_llm_factory=lambda: sentinel)
        result = ctx.get_llm()
        assert result is sentinel

    def test_get_llm_with_factory_and_model_id(self) -> None:
        calls: list[str | None] = []

        def factory(model_id: str | None = None) -> str:
            calls.append(model_id)
            return f"llm:{model_id}"

        ctx = SkillContext(_llm_factory=factory)
        result = ctx.get_llm("deepseek/deepseek-r1:free")
        assert result == "llm:deepseek/deepseek-r1:free"
        assert calls == ["deepseek/deepseek-r1:free"]

    def test_custom_workspace_and_budget(self) -> None:
        ctx = SkillContext(workspace_dir="/tmp/workspace", budget_remaining_usd=2.5)
        assert ctx.workspace_dir == "/tmp/workspace"
        assert ctx.budget_remaining_usd == 2.5


class TestSkillResult:
    """SkillResult creation and defaults."""

    def test_success_result(self) -> None:
        result = SkillResult(skill_name="test", success=True, output="hello")
        assert result.skill_name == "test"
        assert result.success is True
        assert result.output == "hello"
        assert result.error == ""
        assert result.cost_usd == 0.0
        assert result.metadata == {}

    def test_failure_result(self) -> None:
        result = SkillResult(skill_name="test", success=False, error="something broke")
        assert result.success is False
        assert result.error == "something broke"
        assert result.output == ""

    def test_with_metadata(self) -> None:
        result = SkillResult(
            skill_name="test",
            success=True,
            output="data",
            cost_usd=0.05,
            metadata={"tokens": 100},
        )
        assert result.cost_usd == 0.05
        assert result.metadata == {"tokens": 100}
