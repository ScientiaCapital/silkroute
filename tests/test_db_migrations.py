"""Tests for db/migrations.py — the sql/migrations/*.sql runner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from silkroute.db.migrations import (
    Migration,
    _discover_migrations,
    apply_migrations,
    list_pending_migrations,
)


@pytest.fixture
def mock_pool() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def migrations_dir(tmp_path: Path) -> Path:
    (tmp_path / "0001_first.sql").write_text("CREATE TABLE IF NOT EXISTS a (id INT);")
    (tmp_path / "0002_second.sql").write_text("CREATE TABLE IF NOT EXISTS b (id INT);")
    (tmp_path / "not_a_migration.txt").write_text("ignore me")
    return tmp_path


class TestDiscoverMigrations:
    def test_finds_and_sorts_by_version(self, migrations_dir: Path) -> None:
        migrations = _discover_migrations(migrations_dir)
        assert [m.version for m in migrations] == [1, 2]

    def test_ignores_non_matching_files(self, migrations_dir: Path) -> None:
        migrations = _discover_migrations(migrations_dir)
        assert all(m.name.endswith(".sql") for m in migrations)
        assert len(migrations) == 2

    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        assert _discover_migrations(empty) == []

    def test_missing_dir_returns_empty(self, tmp_path: Path) -> None:
        assert _discover_migrations(tmp_path / "does-not-exist") == []


class TestListPendingMigrations:
    async def test_ensures_tracking_table(self, mock_pool: AsyncMock, migrations_dir: Path) -> None:
        mock_pool.fetch.return_value = []
        await list_pending_migrations(mock_pool, migrations_dir)
        create_sql = mock_pool.execute.call_args[0][0]
        assert "CREATE TABLE IF NOT EXISTS schema_migrations" in create_sql

    async def test_excludes_already_applied(self, mock_pool: AsyncMock, migrations_dir: Path) -> None:
        mock_pool.fetch.return_value = [{"version": 1}]
        pending = await list_pending_migrations(mock_pool, migrations_dir)
        assert [m.version for m in pending] == [2]

    async def test_all_pending_when_none_applied(
        self, mock_pool: AsyncMock, migrations_dir: Path,
    ) -> None:
        mock_pool.fetch.return_value = []
        pending = await list_pending_migrations(mock_pool, migrations_dir)
        assert [m.version for m in pending] == [1, 2]


class TestApplyMigrations:
    def _mock_conn(self) -> MagicMock:
        conn = MagicMock()
        conn.execute = AsyncMock()
        transaction_cm = MagicMock()
        transaction_cm.__aenter__ = AsyncMock(return_value=None)
        transaction_cm.__aexit__ = AsyncMock(return_value=False)
        conn.transaction = MagicMock(return_value=transaction_cm)
        return conn

    async def test_applies_all_pending_in_order(
        self, mock_pool: AsyncMock, migrations_dir: Path,
    ) -> None:
        mock_pool.fetch.return_value = []
        conn = self._mock_conn()
        acquire_cm = MagicMock()
        acquire_cm.__aenter__ = AsyncMock(return_value=conn)
        acquire_cm.__aexit__ = AsyncMock(return_value=False)
        # pool.acquire() is sync (returns a context manager, not a coroutine) —
        # override AsyncMock's default of making every attribute awaitable.
        mock_pool.acquire = MagicMock(return_value=acquire_cm)

        applied = await apply_migrations(mock_pool, migrations_dir)

        assert [m.version for m in applied] == [1, 2]
        # 2 migrations x 2 execute calls each (DDL + tracking insert)
        assert conn.execute.await_count == 4

    async def test_no_op_when_up_to_date(self, mock_pool: AsyncMock, migrations_dir: Path) -> None:
        mock_pool.fetch.return_value = [{"version": 1}, {"version": 2}]
        applied = await apply_migrations(mock_pool, migrations_dir)
        assert applied == []
        mock_pool.acquire.assert_not_called()


class TestMigrationNamedTuple:
    def test_fields(self, tmp_path: Path) -> None:
        m = Migration(version=1, name="0001_x.sql", path=tmp_path / "0001_x.sql")
        assert m.version == 1
        assert m.name == "0001_x.sql"
