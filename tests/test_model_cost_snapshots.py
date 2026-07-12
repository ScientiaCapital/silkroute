"""Tests for db/repositories/model_cost_snapshots.py — per-model daily rollup."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock

import pytest

from silkroute.db.repositories.model_cost_snapshots import (
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

    async def test_sql_contains_insert_into_model_cost_snapshots(
        self, mock_pool: AsyncMock
    ) -> None:
        date = datetime.date(2026, 3, 1)
        await rollup_day(mock_pool, date)
        sql = mock_pool.execute.call_args[0][0]
        assert "INSERT INTO model_cost_snapshots" in sql

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

    async def test_sql_contains_group_by_model_and_provider(
        self, mock_pool: AsyncMock
    ) -> None:
        date = datetime.date(2026, 3, 1)
        await rollup_day(mock_pool, date)
        sql = mock_pool.execute.call_args[0][0]
        assert "GROUP BY project_id, model_id, provider" in sql

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
                "model_id": "ollama/qwen2.5:14b",
                "provider": "ollama",
                "snapshot_date": datetime.date(2026, 3, 1),
                "total_cost_usd": 0.0,
                "total_requests": 7,
                "total_tokens": 23029,
            }
        ]
        result = await get_snapshots(
            mock_pool,
            "proj-1",
            datetime.date(2026, 3, 1),
            datetime.date(2026, 3, 7),
        )
        assert len(result) == 1
        assert result[0]["model_id"] == "ollama/qwen2.5:14b"

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
