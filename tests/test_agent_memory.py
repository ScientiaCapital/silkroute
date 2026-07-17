"""Tests for agent/memory.py — recall, prompt formatting, and the remember tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from silkroute.agent.memory import format_memory_block, make_remember_tool, recall_for_session
from silkroute.agent.prompts import build_system_prompt
from silkroute.config.settings import MemoryConfig


@pytest.fixture
def mock_pool() -> AsyncMock:
    return AsyncMock()


class TestRecallForSession:
    async def test_returns_empty_when_pool_none(self) -> None:
        result = await recall_for_session(None, "proj-1", MemoryConfig())
        assert result == []

    async def test_returns_empty_when_disabled(self, mock_pool: AsyncMock) -> None:
        result = await recall_for_session(mock_pool, "proj-1", MemoryConfig(enabled=False))
        assert result == []
        mock_pool.fetch.assert_not_called()

    async def test_returns_empty_on_db_error(self, mock_pool: AsyncMock) -> None:
        with patch(
            "silkroute.db.repositories.memories.recall_memories",
            new=AsyncMock(side_effect=RuntimeError("db down")),
        ):
            result = await recall_for_session(mock_pool, "proj-1", MemoryConfig())
        assert result == []

    async def test_returns_recalled_rows(self, mock_pool: AsyncMock) -> None:
        rows = [{"id": 1, "kind": "fact", "content": "x", "token_estimate": 5}]
        with patch(
            "silkroute.db.repositories.memories.recall_memories",
            new=AsyncMock(return_value=rows),
        ):
            result = await recall_for_session(mock_pool, "proj-1", MemoryConfig())
        assert result == rows

    async def test_drops_entries_over_token_budget(self, mock_pool: AsyncMock) -> None:
        rows = [
            {"id": 1, "kind": "fact", "content": "a", "token_estimate": 400},
            {"id": 2, "kind": "fact", "content": "b", "token_estimate": 400},
        ]
        cfg = MemoryConfig(recall_max_tokens=500)
        with patch(
            "silkroute.db.repositories.memories.recall_memories",
            new=AsyncMock(return_value=rows),
        ):
            result = await recall_for_session(mock_pool, "proj-1", cfg)
        assert len(result) == 1
        assert result[0]["id"] == 1


class TestFormatMemoryBlock:
    def test_empty_when_no_memories(self) -> None:
        assert format_memory_block([]) == ""

    def test_includes_kind_and_content(self) -> None:
        block = format_memory_block([{"kind": "preference", "content": "concise commits"}])
        assert "## Memory" in block
        assert "[preference] concise commits" in block


class TestMakeRememberTool:
    def test_tool_spec_shape(self, mock_pool: AsyncMock) -> None:
        tool = make_remember_tool(mock_pool, "proj-1", "sess-1")
        assert tool.name == "remember"
        assert "content" in tool.parameters["properties"]
        assert tool.parameters["required"] == ["content"]

    async def test_handler_saves_and_returns_confirmation(self, mock_pool: AsyncMock) -> None:
        tool = make_remember_tool(mock_pool, "proj-1", "sess-1")
        with patch(
            "silkroute.db.repositories.memories.insert_memory",
            new=AsyncMock(return_value={"id": 1}),
        ) as mock_insert:
            result = await tool.handler(content="User likes dark mode", kind="preference")
        assert result == "Memory saved."
        mock_insert.assert_awaited_once()
        assert mock_insert.call_args.kwargs["project_id"] == "proj-1"

    async def test_global_scope_passes_project_id_none(self, mock_pool: AsyncMock) -> None:
        tool = make_remember_tool(mock_pool, "proj-1", "sess-1")
        with patch(
            "silkroute.db.repositories.memories.insert_memory",
            new=AsyncMock(return_value={"id": 1}),
        ) as mock_insert:
            await tool.handler(content="x", scope="global")
        assert mock_insert.call_args.kwargs["project_id"] is None

    async def test_handler_never_raises_on_db_error(self, mock_pool: AsyncMock) -> None:
        tool = make_remember_tool(mock_pool, "proj-1", "sess-1")
        with patch(
            "silkroute.db.repositories.memories.insert_memory",
            new=AsyncMock(side_effect=RuntimeError("db down")),
        ):
            result = await tool.handler(content="x")
        assert result.startswith("Error:")


class TestBuildSystemPromptMemorySection:
    def _base_kwargs(self) -> dict:
        return dict(
            project_id="proj-1",
            workspace_dir="/tmp/ws",
            model_name="deepseek-v3",
            budget_remaining=1.0,
            max_iterations=10,
            current_iteration=1,
            task="do something",
        )

    def test_no_memory_section_when_empty(self) -> None:
        prompt = build_system_prompt(**self._base_kwargs())
        assert "## Memory" not in prompt

    def test_includes_memory_section_when_present(self) -> None:
        block = format_memory_block([{"kind": "fact", "content": "x"}])
        prompt = build_system_prompt(**self._base_kwargs(), memories_block=block)
        assert "## Memory" in prompt
        assert "[fact] x" in prompt
