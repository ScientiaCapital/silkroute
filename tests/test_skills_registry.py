"""Tests for mantis/skills/registry.py — SkillRegistry."""

from __future__ import annotations

from typing import Any

import pytest

from silkroute.agent.tools import ToolRegistry
from silkroute.mantis.skills.models import (
    SkillCategory,
    SkillContext,
    SkillResult,
    SkillSpec,
)
from silkroute.mantis.skills.registry import SkillRegistry


def _make_skill(
    name: str = "test_skill",
    category: SkillCategory = SkillCategory.SEARCH,
    output: str = "result",
    raise_exc: bool = False,
) -> SkillSpec:
    async def _handler(_skill_ctx: SkillContext | None = None, **kwargs: Any) -> str:
        if raise_exc:
            raise RuntimeError("handler error")
        return output

    return SkillSpec(
        name=name,
        description=f"Description of {name}",
        category=category,
        parameters={"type": "object", "properties": {}},
        handler=_handler,
    )


class TestSkillRegistryRegisterGet:
    """register() and get() basic behavior."""

    def test_register_and_get(self) -> None:
        reg = SkillRegistry()
        skill = _make_skill("my_skill")
        reg.register(skill)
        retrieved = reg.get("my_skill")
        assert retrieved is skill

    def test_get_missing_returns_none(self) -> None:
        reg = SkillRegistry()
        assert reg.get("nonexistent") is None

    def test_register_overwrites(self) -> None:
        reg = SkillRegistry()
        skill_a = _make_skill("dup", output="a")
        skill_b = _make_skill("dup", output="b")
        reg.register(skill_a)
        reg.register(skill_b)
        assert reg.get("dup") is skill_b


class TestSkillRegistryList:
    """list_skills() with and without category filter."""

    def test_list_all(self) -> None:
        reg = SkillRegistry()
        reg.register(_make_skill("s1", SkillCategory.CODE))
        reg.register(_make_skill("s2", SkillCategory.WEB))
        reg.register(_make_skill("s3", SkillCategory.CODE))
        skills = reg.list_skills()
        assert len(skills) == 3

    def test_list_with_category_filter(self) -> None:
        reg = SkillRegistry()
        reg.register(_make_skill("code1", SkillCategory.CODE))
        reg.register(_make_skill("web1", SkillCategory.WEB))
        reg.register(_make_skill("code2", SkillCategory.CODE))
        code_skills = reg.list_skills(SkillCategory.CODE)
        assert len(code_skills) == 2
        assert all(s.category == SkillCategory.CODE for s in code_skills)

    def test_list_empty_registry(self) -> None:
        reg = SkillRegistry()
        assert reg.list_skills() == []

    def test_list_no_match_returns_empty(self) -> None:
        reg = SkillRegistry()
        reg.register(_make_skill("s1", SkillCategory.CODE))
        assert reg.list_skills(SkillCategory.DOCS) == []


class TestSkillRegistryExecute:
    """execute() success, missing skill, and error handling."""

    async def test_execute_success(self) -> None:
        reg = SkillRegistry()
        reg.register(_make_skill("grepper", output="found it"))
        ctx = SkillContext()
        result = await reg.execute("grepper", ctx)
        assert isinstance(result, SkillResult)
        assert result.success is True
        assert result.output == "found it"
        assert result.skill_name == "grepper"

    async def test_execute_missing_skill(self) -> None:
        reg = SkillRegistry()
        ctx = SkillContext()
        result = await reg.execute("phantom", ctx)
        assert result.success is False
        assert "phantom" in result.error
        assert result.skill_name == "phantom"

    async def test_execute_handler_raises(self) -> None:
        reg = SkillRegistry()
        reg.register(_make_skill("broken", raise_exc=True))
        ctx = SkillContext()
        result = await reg.execute("broken", ctx)
        assert result.success is False
        assert "handler error" in result.error

    async def test_execute_passes_kwargs(self) -> None:
        received_kwargs: dict[str, Any] = {}

        async def _capturing_handler(_skill_ctx: SkillContext | None = None, **kwargs: Any) -> str:
            received_kwargs.update(kwargs)
            return "ok"

        skill = SkillSpec(
            name="kw_skill",
            description="Captures kwargs",
            category=SkillCategory.SYSTEM,
            parameters={"type": "object", "properties": {}},
            handler=_capturing_handler,
        )
        reg = SkillRegistry()
        reg.register(skill)
        ctx = SkillContext()
        await reg.execute("kw_skill", ctx, alpha="hello", beta=42)
        assert received_kwargs == {"alpha": "hello", "beta": 42}


class TestSkillRegistryMount:
    """mount() bridges skills to ToolRegistry."""

    async def test_mount_registers_tools(self) -> None:
        skill_reg = SkillRegistry()
        skill_reg.register(_make_skill("skill_a", output="a_output"))
        skill_reg.register(_make_skill("skill_b", output="b_output"))

        tool_reg = ToolRegistry()
        ctx = SkillContext()
        skill_reg.mount(tool_reg, ctx)

        assert "skill_a" in tool_reg.tool_names
        assert "skill_b" in tool_reg.tool_names

    async def test_mount_handler_injects_skill_context(self) -> None:
        captured_ctx: list[SkillContext | None] = []

        async def _ctx_capturing_handler(
            _skill_ctx: SkillContext | None = None, **kwargs: Any
        ) -> str:
            captured_ctx.append(_skill_ctx)
            return "captured"

        skill = SkillSpec(
            name="ctx_skill",
            description="Captures ctx",
            category=SkillCategory.SYSTEM,
            parameters={"type": "object", "properties": {}},
            handler=_ctx_capturing_handler,
        )

        skill_reg = SkillRegistry()
        skill_reg.register(skill)

        tool_reg = ToolRegistry()
        ctx = SkillContext(workspace_dir="/test/workspace", budget_remaining_usd=3.0)
        skill_reg.mount(tool_reg, ctx)

        # Execute through the tool registry
        result = await tool_reg.execute("ctx_skill", {})
        assert result == "captured"
        assert len(captured_ctx) == 1
        injected_ctx = captured_ctx[0]
        assert injected_ctx is ctx
        assert injected_ctx.workspace_dir == "/test/workspace"

    async def test_mount_tool_description_preserved(self) -> None:
        skill = _make_skill("described_skill")
        skill_reg = SkillRegistry()
        skill_reg.register(skill)

        tool_reg = ToolRegistry()
        ctx = SkillContext()
        skill_reg.mount(tool_reg, ctx)

        tool = tool_reg.get("described_skill")
        assert tool is not None
        assert tool.description == skill.description

    async def test_mount_multiple_skills_independent(self) -> None:
        """Each mounted skill's handler correctly delegates to its own skill."""
        skill_reg = SkillRegistry()
        skill_reg.register(_make_skill("alpha", output="ALPHA"))
        skill_reg.register(_make_skill("beta", output="BETA"))

        tool_reg = ToolRegistry()
        ctx = SkillContext()
        skill_reg.mount(tool_reg, ctx)

        alpha_result = await tool_reg.execute("alpha", {})
        beta_result = await tool_reg.execute("beta", {})
        assert alpha_result == "ALPHA"
        assert beta_result == "BETA"
