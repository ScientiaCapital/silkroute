"""Tests for silkroute.db.repositories.projects — project budget queries."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from silkroute.db.repositories.projects import get_monthly_spend, get_project_budget


@pytest.fixture
def mock_pool() -> AsyncMock:
    return AsyncMock()


async def test_get_project_budget_returns_budget(mock_pool: AsyncMock) -> None:
    """Returns budget_monthly_usd when project exists."""
    mock_pool.fetchrow.return_value = {"budget_monthly_usd": 2.85}

    result = await get_project_budget(mock_pool, "test-project")

    assert result == pytest.approx(2.85)
    mock_pool.fetchrow.assert_awaited_once()


async def test_get_project_budget_returns_none_for_missing(mock_pool: AsyncMock) -> None:
    """Returns None when project doesn't exist."""
    mock_pool.fetchrow.return_value = None

    result = await get_project_budget(mock_pool, "nonexistent")

    assert result is None


async def test_get_monthly_spend_returns_spend(mock_pool: AsyncMock) -> None:
    """Returns spent_this_month from v_budget_remaining view."""
    mock_pool.fetchrow.return_value = {"spent": 1.50}

    result = await get_monthly_spend(mock_pool, "test-project")

    assert result == pytest.approx(1.50)


async def test_get_monthly_spend_returns_zero_for_no_records(mock_pool: AsyncMock) -> None:
    """Returns 0.0 when no cost records exist this month."""
    mock_pool.fetchrow.return_value = None

    result = await get_monthly_spend(mock_pool, "new-project")

    assert result == 0.0


async def test_get_project_budget_queries_correct_table(mock_pool: AsyncMock) -> None:
    """Query targets the projects table."""
    mock_pool.fetchrow.return_value = {"budget_monthly_usd": 200.0}

    await get_project_budget(mock_pool, "default")

    sql = mock_pool.fetchrow.call_args[0][0]
    assert "projects" in sql
    assert "budget_monthly_usd" in sql


async def test_get_monthly_spend_queries_budget_view(mock_pool: AsyncMock) -> None:
    """Query targets the v_budget_remaining view."""
    mock_pool.fetchrow.return_value = {"spent": 0.0}

    await get_monthly_spend(mock_pool, "default")

    sql = mock_pool.fetchrow.call_args[0][0]
    assert "v_budget_remaining" in sql
