"""Tests for db/repositories/skill_executions.py — skill execution persistence."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from silkroute.db.repositories.skill_executions import (
    get_skill_execution_stats,
    insert_skill_execution,
    list_skill_executions,
)


@pytest.fixture
def mock_pool() -> AsyncMock:
    return AsyncMock()


class TestInsertSkillExecution:
    async def test_inserts_and_returns_dict(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetchrow.return_value = {
            "id": 1,
            "skill_name": "web_search",
            "session_id": "sess-1",
            "project_id": "proj-1",
            "success": True,
            "cost_usd": 0.01,
        }
        result = await insert_skill_execution(
            mock_pool, "web_search", "sess-1", "proj-1", success=True, cost_usd=0.01,
        )
        assert result["skill_name"] == "web_search"
        assert result["success"] is True
        mock_pool.fetchrow.assert_awaited_once()

    async def test_sql_contains_insert(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetchrow.return_value = {"id": 1, "skill_name": "code"}
        await insert_skill_execution(mock_pool, "code", "s1", "p1", success=True)
        sql = mock_pool.fetchrow.call_args[0][0]
        assert "INSERT INTO skill_executions" in sql
        assert "RETURNING" in sql

    async def test_truncates_output_text(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetchrow.return_value = {"id": 1, "skill_name": "code"}
        long_output = "x" * 5000
        await insert_skill_execution(
            mock_pool, "code", "s1", "p1", success=True, output_text=long_output,
        )
        # The 8th positional arg is output_text (after the SQL string)
        args = mock_pool.fetchrow.call_args[0]
        assert len(args[8]) == 2000

    async def test_default_input_json(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetchrow.return_value = {"id": 1, "skill_name": "s"}
        await insert_skill_execution(mock_pool, "s", "s1", "p1", success=False)
        args = mock_pool.fetchrow.call_args[0]
        assert args[7] == "{}"  # json.dumps({})


class TestListSkillExecutions:
    async def test_returns_list(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = [
            {"id": 1, "skill_name": "web_search"},
            {"id": 2, "skill_name": "code"},
        ]
        result = await list_skill_executions(mock_pool)
        assert len(result) == 2

    async def test_filters_by_skill_name(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = []
        await list_skill_executions(mock_pool, skill_name="web_search")
        sql = mock_pool.fetch.call_args[0][0]
        assert "skill_name" in sql

    async def test_filters_by_project_id(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = []
        await list_skill_executions(mock_pool, project_id="proj-1")
        sql = mock_pool.fetch.call_args[0][0]
        assert "project_id" in sql

    async def test_filters_by_session_id(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = []
        await list_skill_executions(mock_pool, session_id="sess-1")
        sql = mock_pool.fetch.call_args[0][0]
        assert "session_id" in sql

    async def test_orders_by_created_at_desc(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = []
        await list_skill_executions(mock_pool)
        sql = mock_pool.fetch.call_args[0][0]
        assert "ORDER BY created_at DESC" in sql

    async def test_empty_list(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = []
        result = await list_skill_executions(mock_pool)
        assert result == []


class TestGetSkillExecutionStats:
    async def test_returns_stats(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = [
            {"skill_name": "web_search", "execution_count": 10, "total_cost_usd": 0.50},
        ]
        result = await get_skill_execution_stats(mock_pool)
        assert len(result) == 1
        assert result[0]["skill_name"] == "web_search"

    async def test_filters_by_project_id(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = []
        await get_skill_execution_stats(mock_pool, project_id="proj-1")
        sql = mock_pool.fetch.call_args[0][0]
        assert "project_id" in sql
        assert "GROUP BY skill_name" in sql

    async def test_no_filter_groups_all(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = []
        await get_skill_execution_stats(mock_pool)
        sql = mock_pool.fetch.call_args[0][0]
        assert "GROUP BY skill_name" in sql
