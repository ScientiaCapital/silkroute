"""Tests for project CRUD functions in silkroute.db.repositories.projects."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from silkroute.db.repositories.projects import (
    create_project,
    delete_project,
    get_project,
    list_projects,
    update_project,
)


@pytest.fixture
def mock_pool() -> AsyncMock:
    return AsyncMock()


class TestCreateProject:
    async def test_creates_and_returns_dict(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetchrow.return_value = {
            "id": "test-proj",
            "name": "Test Project",
            "description": "",
            "github_repo": "",
            "budget_monthly_usd": 2.85,
            "budget_daily_usd": 0.10,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        result = await create_project(mock_pool, "test-proj", "Test Project")
        assert result["id"] == "test-proj"
        assert result["name"] == "Test Project"
        mock_pool.fetchrow.assert_awaited_once()

    async def test_passes_all_fields(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetchrow.return_value = {"id": "x", "name": "X", "description": "desc",
            "github_repo": "org/repo", "budget_monthly_usd": 5.0, "budget_daily_usd": 1.0,
            "created_at": "", "updated_at": ""}
        await create_project(mock_pool, "x", "X", description="desc",
            github_repo="org/repo", budget_monthly_usd=5.0, budget_daily_usd=1.0)
        sql = mock_pool.fetchrow.call_args[0][0]
        assert "INSERT INTO projects" in sql
        assert "RETURNING" in sql

    async def test_default_budgets(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetchrow.return_value = {"id": "d", "name": "D", "description": "",
            "github_repo": "", "budget_monthly_usd": 2.85, "budget_daily_usd": 0.10,
            "created_at": "", "updated_at": ""}
        await create_project(mock_pool, "d", "D")
        args = mock_pool.fetchrow.call_args[0]
        assert args[5] == 2.85  # budget_monthly_usd default
        assert args[6] == 0.10  # budget_daily_usd default


class TestListProjects:
    async def test_returns_list_of_dicts(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = [
            {"id": "a", "name": "A"},
            {"id": "b", "name": "B"},
        ]
        result = await list_projects(mock_pool)
        assert len(result) == 2
        assert result[0]["id"] == "a"

    async def test_empty_list(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = []
        result = await list_projects(mock_pool)
        assert result == []

    async def test_orders_by_created_at_desc(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = []
        await list_projects(mock_pool)
        sql = mock_pool.fetch.call_args[0][0]
        assert "ORDER BY created_at DESC" in sql


class TestGetProject:
    async def test_returns_dict_when_found(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetchrow.return_value = {"id": "test", "name": "Test"}
        result = await get_project(mock_pool, "test")
        assert result is not None
        assert result["id"] == "test"

    async def test_returns_none_when_not_found(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetchrow.return_value = None
        result = await get_project(mock_pool, "nonexistent")
        assert result is None


class TestUpdateProject:
    async def test_partial_update_name(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetchrow.return_value = {"id": "p", "name": "New Name"}
        result = await update_project(mock_pool, "p", name="New Name")
        assert result is not None
        assert result["name"] == "New Name"
        sql = mock_pool.fetchrow.call_args[0][0]
        assert "UPDATE projects SET" in sql
        assert "name" in sql

    async def test_no_changes_returns_existing(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetchrow.return_value = {"id": "p", "name": "Original"}
        result = await update_project(mock_pool, "p")
        assert result is not None
        # Should call get_project path (SELECT not UPDATE)
        sql = mock_pool.fetchrow.call_args[0][0]
        assert "SELECT" in sql

    async def test_returns_none_when_not_found(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetchrow.return_value = None
        result = await update_project(mock_pool, "ghost", name="X")
        assert result is None

    async def test_updates_multiple_fields(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetchrow.return_value = {"id": "p", "name": "N", "budget_monthly_usd": 10.0}
        await update_project(mock_pool, "p", name="N", budget_monthly_usd=10.0)
        sql = mock_pool.fetchrow.call_args[0][0]
        assert "name" in sql
        assert "budget_monthly_usd" in sql


class TestDeleteProject:
    async def test_deletes_and_returns_true(self, mock_pool: AsyncMock) -> None:
        mock_pool.execute.return_value = "DELETE 1"
        result = await delete_project(mock_pool, "test-proj")
        assert result is True

    async def test_returns_false_when_not_found(self, mock_pool: AsyncMock) -> None:
        mock_pool.execute.return_value = "DELETE 0"
        result = await delete_project(mock_pool, "nonexistent")
        assert result is False

    async def test_blocks_default_deletion(self, mock_pool: AsyncMock) -> None:
        with pytest.raises(ValueError, match="default"):
            await delete_project(mock_pool, "default")

    async def test_fk_violation_raises_value_error(self, mock_pool: AsyncMock) -> None:
        import asyncpg
        mock_pool.execute.side_effect = asyncpg.ForeignKeyViolationError("")
        with pytest.raises(ValueError, match="associated cost records"):
            await delete_project(mock_pool, "has-costs")
