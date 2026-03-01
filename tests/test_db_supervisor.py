"""Tests for db/repositories/supervisor.py — supervisor session CRUD.

Uses unittest.mock AsyncMock to simulate asyncpg.Pool.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from silkroute.db.repositories.supervisor import (
    _row_to_session,
    create_supervisor_session,
    delete_supervisor_session,
    get_supervisor_session,
    list_supervisor_sessions,
    update_checkpoint,
    update_supervisor_session,
)
from silkroute.mantis.supervisor.models import (
    SessionStatus,
    SupervisorCheckpoint,
    SupervisorPlan,
    SupervisorSession,
    SupervisorStep,
)


def _make_session(session_id: str = "sess-1") -> SupervisorSession:
    return SupervisorSession(
        id=session_id,
        project_id="default",
        status=SessionStatus.PENDING,
        plan=SupervisorPlan(
            id="plan-1",
            steps=[SupervisorStep(id="a", name="step1")],
        ),
    )


def _make_row(session_id: str = "sess-1") -> dict:
    """Simulate an asyncpg.Record as a dict for testing."""
    return {
        "id": session_id,
        "project_id": "default",
        "status": "pending",
        "plan_json": {"id": "plan-1", "steps": [{"id": "a", "name": "step1"}]},
        "checkpoint_json": None,
        "context_json": {},
        "total_cost_usd": 0.0,
        "config_json": {},
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "error": "",
    }


class TestCreateSupervisorSession:
    async def test_inserts_session(self):
        pool = AsyncMock()
        session = _make_session()
        await create_supervisor_session(pool, session)
        pool.execute.assert_called_once()
        args = pool.execute.call_args[0]
        assert "INSERT INTO supervisor_sessions" in args[0]
        assert args[1] == "sess-1"


class TestUpdateSupervisorSession:
    async def test_updates_session(self):
        pool = AsyncMock()
        session = _make_session()
        session.status = SessionStatus.RUNNING
        await update_supervisor_session(pool, session)
        pool.execute.assert_called_once()
        args = pool.execute.call_args[0]
        assert "UPDATE supervisor_sessions" in args[0]
        assert args[2] == "running"


class TestGetSupervisorSession:
    async def test_returns_session(self):
        pool = AsyncMock()
        pool.fetchrow.return_value = _make_row()
        result = await get_supervisor_session(pool, "sess-1")
        assert result is not None
        assert result.id == "sess-1"
        assert result.status == SessionStatus.PENDING

    async def test_returns_none_if_not_found(self):
        pool = AsyncMock()
        pool.fetchrow.return_value = None
        result = await get_supervisor_session(pool, "nonexistent")
        assert result is None


class TestUpdateCheckpoint:
    async def test_updates_checkpoint(self):
        pool = AsyncMock()
        cp = SupervisorCheckpoint(
            session_id="sess-1",
            plan_json={"id": "plan-1"},
            total_cost_usd=1.5,
        )
        await update_checkpoint(pool, "sess-1", cp, 1.5)
        pool.execute.assert_called_once()
        args = pool.execute.call_args[0]
        assert "checkpoint_json" in args[0]


class TestListSupervisorSessions:
    async def test_list_no_filters(self):
        pool = AsyncMock()
        pool.fetch.return_value = [_make_row("s1"), _make_row("s2")]
        result = await list_supervisor_sessions(pool)
        assert len(result) == 2

    async def test_list_with_project_filter(self):
        pool = AsyncMock()
        pool.fetch.return_value = [_make_row()]
        result = await list_supervisor_sessions(pool, project_id="default")
        assert len(result) == 1
        call_args = pool.fetch.call_args[0]
        assert "project_id" in call_args[0]

    async def test_list_with_status_filter(self):
        pool = AsyncMock()
        pool.fetch.return_value = []
        result = await list_supervisor_sessions(pool, status="running")
        assert result == []


class TestDeleteSupervisorSession:
    async def test_deletes_existing(self):
        pool = AsyncMock()
        pool.execute.return_value = "DELETE 1"
        result = await delete_supervisor_session(pool, "sess-1")
        assert result is True

    async def test_returns_false_if_not_found(self):
        pool = AsyncMock()
        pool.execute.return_value = "DELETE 0"
        result = await delete_supervisor_session(pool, "nonexistent")
        assert result is False


class TestRowToSession:
    def test_basic_conversion(self):
        row = _make_row()
        session = _row_to_session(row)
        assert session.id == "sess-1"
        assert session.project_id == "default"
        assert session.status == SessionStatus.PENDING
        assert len(session.plan.steps) == 1

    def test_with_checkpoint(self):
        row = _make_row()
        row["checkpoint_json"] = {
            "session_id": "sess-1",
            "plan_json": {},
            "context_json": {},
            "step_results": {"a": "done"},
            "total_cost_usd": 0.5,
        }
        session = _row_to_session(row)
        assert session.checkpoint is not None
        assert session.checkpoint.total_cost_usd == 0.5
