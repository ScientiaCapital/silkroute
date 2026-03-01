"""Tests for db/repositories/budget_snapshots.py — daily rollup persistence."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, call

import pytest

from silkroute.db.repositories.budget_snapshots import (
    backfill,
    get_snapshots,
    rollup_day,
)


@pytest.fixture
def mock_pool() -> AsyncMock:
    return AsyncMock()


class TestRollupDay:
    async def test_calls_pool_execute(self, mock_pool: AsyncMock) -> None:
        date = datetime.date(2026, 3, 1)
        await rollup_day(mock_pool, date)
        mock_pool.execute.assert_awaited_once()

    async def test_passes_date_as_first_positional_arg(self, mock_pool: AsyncMock) -> None:
        date = datetime.date(2026, 3, 1)
        await rollup_day(mock_pool, date)
        args = mock_pool.execute.call_args[0]
        assert args[1] == date

    async def test_sql_contains_insert_into_budget_snapshots(
        self, mock_pool: AsyncMock
    ) -> None:
        date = datetime.date(2026, 3, 1)
        await rollup_day(mock_pool, date)
        sql = mock_pool.execute.call_args[0][0]
        assert "INSERT INTO budget_snapshots" in sql

    async def test_sql_contains_on_conflict_upsert(self, mock_pool: AsyncMock) -> None:
        date = datetime.date(2026, 3, 1)
        await rollup_day(mock_pool, date)
        sql = mock_pool.execute.call_args[0][0]
        assert "ON CONFLICT" in sql
        assert "DO UPDATE SET" in sql

    async def test_sql_contains_cost_logs_source(self, mock_pool: AsyncMock) -> None:
        date = datetime.date(2026, 3, 1)
        await rollup_day(mock_pool, date)
        sql = mock_pool.execute.call_args[0][0]
        assert "FROM cost_logs" in sql

    async def test_sql_contains_model_tier_filter(self, mock_pool: AsyncMock) -> None:
        date = datetime.date(2026, 3, 1)
        await rollup_day(mock_pool, date)
        sql = mock_pool.execute.call_args[0][0]
        assert "model_tier" in sql
        assert "free" in sql
        assert "standard" in sql
        assert "premium" in sql

    async def test_sql_contains_group_by_project_id(self, mock_pool: AsyncMock) -> None:
        date = datetime.date(2026, 3, 1)
        await rollup_day(mock_pool, date)
        sql = mock_pool.execute.call_args[0][0]
        assert "GROUP BY project_id" in sql

    async def test_idempotent_upsert_updates_all_columns(
        self, mock_pool: AsyncMock
    ) -> None:
        date = datetime.date(2026, 3, 1)
        await rollup_day(mock_pool, date)
        sql = mock_pool.execute.call_args[0][0]
        assert "total_cost_usd = EXCLUDED.total_cost_usd" in sql
        assert "total_requests = EXCLUDED.total_requests" in sql
        assert "total_tokens = EXCLUDED.total_tokens" in sql


class TestGetSnapshots:
    async def test_returns_list_of_dicts(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = [
            {
                "id": 1,
                "project_id": "proj-1",
                "snapshot_date": datetime.date(2026, 3, 1),
                "total_cost_usd": 0.50,
                "total_requests": 10,
                "total_tokens": 5000,
                "free_requests": 5,
                "free_cost_usd": 0.0,
                "standard_requests": 3,
                "standard_cost_usd": 0.30,
                "premium_requests": 2,
                "premium_cost_usd": 0.20,
            }
        ]
        result = await get_snapshots(
            mock_pool,
            "proj-1",
            datetime.date(2026, 3, 1),
            datetime.date(2026, 3, 7),
        )
        assert len(result) == 1
        assert result[0]["project_id"] == "proj-1"
        assert result[0]["total_cost_usd"] == 0.50

    async def test_returns_empty_list_when_no_rows(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = []
        result = await get_snapshots(
            mock_pool,
            "proj-missing",
            datetime.date(2026, 1, 1),
            datetime.date(2026, 1, 31),
        )
        assert result == []

    async def test_passes_project_id_and_dates_as_params(
        self, mock_pool: AsyncMock
    ) -> None:
        mock_pool.fetch.return_value = []
        start = datetime.date(2026, 2, 1)
        end = datetime.date(2026, 2, 28)
        await get_snapshots(mock_pool, "proj-abc", start, end)
        args = mock_pool.fetch.call_args[0]
        assert args[1] == "proj-abc"
        assert args[2] == start
        assert args[3] == end

    async def test_sql_contains_project_id_filter(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = []
        await get_snapshots(
            mock_pool,
            "proj-1",
            datetime.date(2026, 3, 1),
            datetime.date(2026, 3, 7),
        )
        sql = mock_pool.fetch.call_args[0][0]
        assert "project_id" in sql

    async def test_sql_contains_date_range_filter(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = []
        await get_snapshots(
            mock_pool,
            "proj-1",
            datetime.date(2026, 3, 1),
            datetime.date(2026, 3, 7),
        )
        sql = mock_pool.fetch.call_args[0][0]
        assert "snapshot_date >=" in sql
        assert "snapshot_date <=" in sql

    async def test_sql_orders_by_snapshot_date_asc(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = []
        await get_snapshots(
            mock_pool,
            "proj-1",
            datetime.date(2026, 3, 1),
            datetime.date(2026, 3, 7),
        )
        sql = mock_pool.fetch.call_args[0][0]
        assert "ORDER BY snapshot_date ASC" in sql

    async def test_returns_multiple_rows(self, mock_pool: AsyncMock) -> None:
        mock_pool.fetch.return_value = [
            {"project_id": "proj-1", "snapshot_date": datetime.date(2026, 3, 1)},
            {"project_id": "proj-1", "snapshot_date": datetime.date(2026, 3, 2)},
            {"project_id": "proj-1", "snapshot_date": datetime.date(2026, 3, 3)},
        ]
        result = await get_snapshots(
            mock_pool,
            "proj-1",
            datetime.date(2026, 3, 1),
            datetime.date(2026, 3, 3),
        )
        assert len(result) == 3


class TestBackfill:
    async def test_processes_single_day(self, mock_pool: AsyncMock) -> None:
        date = datetime.date(2026, 3, 1)
        count = await backfill(mock_pool, date, date)
        assert count == 1
        mock_pool.execute.assert_awaited_once()

    async def test_processes_multiple_days(self, mock_pool: AsyncMock) -> None:
        start = datetime.date(2026, 3, 1)
        end = datetime.date(2026, 3, 5)
        count = await backfill(mock_pool, start, end)
        assert count == 5
        assert mock_pool.execute.await_count == 5

    async def test_returns_day_count(self, mock_pool: AsyncMock) -> None:
        start = datetime.date(2026, 2, 1)
        end = datetime.date(2026, 2, 28)
        count = await backfill(mock_pool, start, end)
        assert count == 28

    async def test_calls_rollup_day_for_each_date(self, mock_pool: AsyncMock) -> None:
        start = datetime.date(2026, 3, 1)
        end = datetime.date(2026, 3, 3)
        await backfill(mock_pool, start, end)
        # Each call to pool.execute should have the correct date
        call_dates = [c[0][1] for c in mock_pool.execute.call_args_list]
        assert call_dates == [
            datetime.date(2026, 3, 1),
            datetime.date(2026, 3, 2),
            datetime.date(2026, 3, 3),
        ]

    async def test_sequential_not_parallel(self, mock_pool: AsyncMock) -> None:
        """Verify that each rollup_day is awaited before proceeding to the next."""
        dates_called: list[datetime.date] = []

        async def capture_execute(sql: str, date: datetime.date) -> None:
            dates_called.append(date)

        mock_pool.execute.side_effect = capture_execute

        start = datetime.date(2026, 3, 10)
        end = datetime.date(2026, 3, 12)
        await backfill(mock_pool, start, end)

        assert dates_called == [
            datetime.date(2026, 3, 10),
            datetime.date(2026, 3, 11),
            datetime.date(2026, 3, 12),
        ]
