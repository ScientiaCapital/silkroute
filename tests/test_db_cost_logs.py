"""Tests for silkroute.db.repositories.cost_logs — per-iteration cost insertion."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from silkroute.agent.session import AgentSession, Iteration
from silkroute.db.repositories.cost_logs import insert_cost_log


@pytest.fixture
def mock_pool() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def sample_session() -> AgentSession:
    return AgentSession(
        task="analyze code quality for the repository",
        model_id="deepseek/deepseek-v3.2",
        project_id="test-project",
    )


@pytest.fixture
def sample_iteration() -> Iteration:
    return Iteration(
        number=1,
        thought="Let me check the code structure.",
        cost_usd=0.0025,
        input_tokens=500,
        output_tokens=200,
        latency_ms=1234,
    )


def _get_model() -> object:
    """Get a real ModelSpec from the registry."""
    from silkroute.providers.models import get_model

    model = get_model("deepseek/deepseek-v3.2")
    assert model is not None
    return model


async def test_insert_cost_log_executes_insert(
    mock_pool: AsyncMock,
    sample_session: AgentSession,
    sample_iteration: Iteration,
) -> None:
    """insert_cost_log inserts a row into cost_logs."""
    model = _get_model()

    await insert_cost_log(mock_pool, sample_session, sample_iteration, model)

    mock_pool.execute.assert_awaited_once()
    sql = mock_pool.execute.call_args[0][0]
    assert "INSERT INTO cost_logs" in sql


async def test_insert_cost_log_passes_correct_values(
    mock_pool: AsyncMock,
    sample_session: AgentSession,
    sample_iteration: Iteration,
) -> None:
    """insert_cost_log maps all fields correctly."""
    model = _get_model()

    await insert_cost_log(mock_pool, sample_session, sample_iteration, model)

    args = mock_pool.execute.call_args[0]
    assert args[1] == "test-project"  # project_id
    assert args[2] == "deepseek/deepseek-v3.2"  # model_id
    assert args[3] == "standard"  # model_tier
    assert args[4] == "deepseek"  # provider
    assert args[5] == 500  # input_tokens
    assert args[6] == 200  # output_tokens
    assert args[7] == 700  # total_tokens
    assert args[8] == pytest.approx(0.0025)  # cost_usd
    assert args[11] == 1234  # latency_ms


async def test_insert_cost_log_truncates_task_type(
    mock_pool: AsyncMock,
    sample_iteration: Iteration,
) -> None:
    """task_type is truncated to 100 characters."""
    long_task = "x" * 200
    session = AgentSession(task=long_task, model_id="deepseek/deepseek-v3.2")
    model = _get_model()

    await insert_cost_log(mock_pool, session, sample_iteration, model)

    args = mock_pool.execute.call_args[0]
    assert len(args[9]) == 100  # task_type truncated


async def test_insert_cost_log_includes_session_id(
    mock_pool: AsyncMock,
    sample_session: AgentSession,
    sample_iteration: Iteration,
) -> None:
    """session_id is passed for attribution."""
    model = _get_model()

    await insert_cost_log(mock_pool, sample_session, sample_iteration, model)

    args = mock_pool.execute.call_args[0]
    assert args[10] == sample_session.id  # session_id
