"""Tests for silkroute.db.repositories.sessions — AgentSession persistence."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from silkroute.agent.session import AgentSession, Iteration, SessionStatus
from silkroute.db.repositories.sessions import (
    _STATUS_TO_DB,
    close_session,
    create_session,
    update_session,
)


@pytest.fixture
def mock_pool() -> AsyncMock:
    """Mock asyncpg pool that tracks execute calls."""
    return AsyncMock()


@pytest.fixture
def sample_session() -> AgentSession:
    """A sample session for testing."""
    session = AgentSession(
        task="list files",
        model_id="deepseek/deepseek-v3.2",
        project_id="test-project",
        budget_limit_usd=5.0,
    )
    return session


async def test_create_session_executes_insert(mock_pool: AsyncMock, sample_session: AgentSession) -> None:
    """create_session inserts a row into agent_sessions."""
    await create_session(mock_pool, sample_session)

    mock_pool.execute.assert_awaited_once()
    sql = mock_pool.execute.call_args[0][0]
    assert "INSERT INTO agent_sessions" in sql


async def test_create_session_passes_correct_values(mock_pool: AsyncMock, sample_session: AgentSession) -> None:
    """create_session passes all session fields as parameters."""
    await create_session(mock_pool, sample_session)

    args = mock_pool.execute.call_args[0]
    assert args[1] == sample_session.id
    assert args[2] == sample_session.project_id
    assert args[3] == "active"  # SessionStatus.ACTIVE → 'active'
    assert args[4] == sample_session.task
    assert args[5] == sample_session.model_id


async def test_update_session_executes_update(mock_pool: AsyncMock, sample_session: AgentSession) -> None:
    """update_session updates iteration count and cost."""
    sample_session.add_iteration(Iteration(number=1, cost_usd=0.01, input_tokens=100, output_tokens=50))

    await update_session(mock_pool, sample_session)

    mock_pool.execute.assert_awaited_once()
    sql = mock_pool.execute.call_args[0][0]
    assert "UPDATE agent_sessions" in sql

    args = mock_pool.execute.call_args[0]
    assert args[1] == sample_session.id
    assert args[2] == 1  # iteration_count


async def test_close_session_sets_terminal_status(mock_pool: AsyncMock, sample_session: AgentSession) -> None:
    """close_session updates status and completed_at."""
    sample_session.complete(SessionStatus.COMPLETED)

    await close_session(mock_pool, sample_session)

    mock_pool.execute.assert_awaited_once()
    args = mock_pool.execute.call_args[0]
    assert args[2] == "completed"  # DB status value


async def test_close_session_budget_exceeded_maps_to_failed(mock_pool: AsyncMock, sample_session: AgentSession) -> None:
    """BUDGET_EXCEEDED maps to 'failed' in the DB."""
    sample_session.complete(SessionStatus.BUDGET_EXCEEDED)

    await close_session(mock_pool, sample_session)

    args = mock_pool.execute.call_args[0]
    assert args[2] == "failed"  # BUDGET_EXCEEDED → 'failed'


def test_status_mapping_covers_all_statuses() -> None:
    """All SessionStatus values must be in _STATUS_TO_DB."""
    for status in SessionStatus:
        assert status in _STATUS_TO_DB, f"Missing mapping for {status}"


def test_status_mapping_only_uses_valid_db_values() -> None:
    """All mapped DB values must be in the CHECK constraint set."""
    valid_db_values = {"active", "completed", "failed", "timeout"}
    for status, db_value in _STATUS_TO_DB.items():
        assert db_value in valid_db_values, f"{status} maps to invalid DB value: {db_value}"


async def test_create_session_serializes_messages_as_json(mock_pool: AsyncMock, sample_session: AgentSession) -> None:
    """messages_json parameter should be a JSON string."""
    sample_session.messages = [{"role": "system", "content": "test"}]

    await create_session(mock_pool, sample_session)

    args = mock_pool.execute.call_args[0]
    json_arg = args[8]  # messages_json parameter
    assert isinstance(json_arg, str)
    assert '"role"' in json_arg
