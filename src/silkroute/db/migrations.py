"""Lightweight migration runner for sql/migrations/*.sql.

init.sql remains the fresh-install bootstrap (already contains every
table). Migrations exist for *existing* databases that need to catch up
to schema changes made after their install — each file is numbered
(NNNN_description.sql), applied in order, and tracked in
schema_migrations so it never re-runs. No down-migrations: this project
has no rollback story, matching its "change the code, don't build
backwards-compat shims" convention.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

import asyncpg
import structlog

log = structlog.get_logger()

_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "sql" / "migrations"
_FILENAME_RE = re.compile(r"^(\d+)_.*\.sql$")


class Migration(NamedTuple):
    version: int
    name: str
    path: Path


def _discover_migrations(migrations_dir: Path) -> list[Migration]:
    """Scan migrations_dir for NNNN_description.sql files, sorted by version."""
    if not migrations_dir.is_dir():
        return []
    migrations = []
    for path in migrations_dir.glob("*.sql"):
        match = _FILENAME_RE.match(path.name)
        if not match:
            log.warning("migration_filename_skipped", filename=path.name)
            continue
        migrations.append(Migration(version=int(match.group(1)), name=path.name, path=path))
    return sorted(migrations, key=lambda m: m.version)


async def _ensure_schema_migrations_table(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version     INTEGER PRIMARY KEY,
            name        TEXT NOT NULL,
            applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


async def _applied_versions(pool: asyncpg.Pool) -> set[int]:
    rows = await pool.fetch("SELECT version FROM schema_migrations")
    return {row["version"] for row in rows}


async def list_pending_migrations(
    pool: asyncpg.Pool,
    migrations_dir: Path | None = None,
) -> list[Migration]:
    """Return migrations not yet recorded in schema_migrations, in order."""
    await _ensure_schema_migrations_table(pool)
    applied = await _applied_versions(pool)
    migrations = _discover_migrations(migrations_dir or _MIGRATIONS_DIR)
    return [m for m in migrations if m.version not in applied]


async def apply_migrations(
    pool: asyncpg.Pool,
    migrations_dir: Path | None = None,
) -> list[Migration]:
    """Apply all pending migrations in order. Each runs in its own transaction.

    Returns the migrations that were applied. Raises on the first failure —
    migrations after the failing one are not attempted.
    """
    pending = await list_pending_migrations(pool, migrations_dir)
    if not pending:
        return []

    applied: list[Migration] = []
    async with pool.acquire() as conn:
        for migration in pending:
            sql = migration.path.read_text()
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (version, name) VALUES ($1, $2)",
                    migration.version,
                    migration.name,
                )
            log.info("migration_applied", version=migration.version, name=migration.name)
            applied.append(migration)
    return applied
