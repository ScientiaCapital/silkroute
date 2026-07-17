"""Tests for db/repositories/memories.py — persistent agent memory."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from silkroute.db.repositories.memories import (
    delete_memory,
    insert_memory,
    list_memories,
    mark_recalled,
    recall_memories,
)


@pytest.fixture
def mock_pool() -> AsyncMock:
    return AsyncMock()


class TestInsertMemory:
    async def test_inserts_and_returns_dict(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetchrow.return_value = {
            "id": 1,
            "project_id": "proj-1",
            "kind": "fact",
            "content": "User prefers concise commits",
            "importance": 0.5,
        }
        result = await insert_memory(mock_pool, "User prefers concise commits", project_id="proj-1")
        assert result["content"] == "User prefers concise commits"
        mock_pool.fetchrow.assert_awaited_once()

    async def test_sql_contains_insert_and_conflict(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetchrow.return_value = {"id": 1, "content": "x"}
        await insert_memory(mock_pool, "x")
        sql = mock_pool.fetchrow.call_args[0][0]
        assert "INSERT INTO agent_memories" in sql
        assert "ON CONFLICT" in sql
        assert "RETURNING" in sql

    async def test_truncates_content(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetchrow.return_value = {"id": 1, "content": "x"}
        long_content = "x" * 5000
        await insert_memory(mock_pool, long_content)
        args = mock_pool.fetchrow.call_args[0]
        # positional args: (sql, project_id, kind, content, importance, source_session_id, token_estimate)
        content_arg = args[3]
        assert len(content_arg) == 500

    async def test_defaults_kind_fact(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetchrow.return_value = {"id": 1, "content": "x"}
        await insert_memory(mock_pool, "x")
        args = mock_pool.fetchrow.call_args[0]
        assert args[2] == "fact"

    async def test_global_scope_project_id_none(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetchrow.return_value = {"id": 1, "content": "x"}
        await insert_memory(mock_pool, "x", project_id=None)
        args = mock_pool.fetchrow.call_args[0]
        assert args[1] is None

    async def test_computes_token_estimate(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetchrow.return_value = {"id": 1, "content": "x"}
        await insert_memory(mock_pool, "x" * 40)
        args = mock_pool.fetchrow.call_args[0]
        token_estimate = args[6]
        assert token_estimate == 10  # 40 // 4


class TestListMemories:
    async def test_returns_list(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = [{"id": 1}, {"id": 2}]
        result = await list_memories(mock_pool)
        assert len(result) == 2

    async def test_filters_by_project_id(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = []
        await list_memories(mock_pool, project_id="proj-1")
        sql = mock_pool.fetch.call_args[0][0]
        assert "project_id" in sql

    async def test_filters_by_kind(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = []
        await list_memories(mock_pool, kind="preference")
        sql = mock_pool.fetch.call_args[0][0]
        assert "kind" in sql

    async def test_orders_by_created_at_desc(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = []
        await list_memories(mock_pool)
        sql = mock_pool.fetch.call_args[0][0]
        assert "ORDER BY created_at DESC" in sql

    async def test_empty_list(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = []
        result = await list_memories(mock_pool)
        assert result == []


class TestRecallMemories:
    async def test_returns_list(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = [{"id": 1, "content": "x"}]
        result = await recall_memories(mock_pool, "proj-1")
        assert len(result) == 1

    async def test_sql_includes_project_and_global_scope(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = []
        await recall_memories(mock_pool, "proj-1")
        sql = mock_pool.fetch.call_args[0][0]
        assert "project_id = $1" in sql
        assert "project_id IS NULL" in sql

    async def test_orders_by_importance_desc(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = []
        await recall_memories(mock_pool, "proj-1")
        sql = mock_pool.fetch.call_args[0][0]
        assert "ORDER BY importance DESC" in sql

    async def test_passes_limit(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = []
        await recall_memories(mock_pool, "proj-1", limit=3)
        args = mock_pool.fetch.call_args[0]
        assert args[-1] == 3


class TestMarkRecalled:
    async def test_updates_recall_count(self, mock_pool: AsyncMock) -> None:
        await mark_recalled(mock_pool, [1, 2, 3])
        mock_pool.execute.assert_awaited_once()
        sql = mock_pool.execute.call_args[0][0]
        assert "recall_count = recall_count + 1" in sql

    async def test_no_op_for_empty_list(self, mock_pool: AsyncMock) -> None:
        await mark_recalled(mock_pool, [])
        mock_pool.execute.assert_not_awaited()


class TestDeleteMemory:
    async def test_returns_true_when_deleted(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetchrow.return_value = {"id": 1}
        result = await delete_memory(mock_pool, 1)
        assert result is True

    async def test_returns_false_when_missing(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetchrow.return_value = None
        result = await delete_memory(mock_pool, 999)
        assert result is False
