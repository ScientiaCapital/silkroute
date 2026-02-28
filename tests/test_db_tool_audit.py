"""Tests for db/repositories/tool_audit.py — tool audit log persistence."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from silkroute.agent.session import AgentSession, Iteration, ToolCall
from silkroute.db.repositories.tool_audit import insert_tool_audit_logs


@pytest.fixture
def mock_pool() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def session() -> AgentSession:
    return AgentSession(
        task="test task",
        model_id="test/model",
        project_id="default",
        budget_limit_usd=1.0,
    )


class TestInsertToolAuditLogs:
    """insert_tool_audit_logs persistence tests."""

    @pytest.mark.asyncio
    async def test_inserts_tool_calls(self, mock_pool, session):
        """Should INSERT rows for each tool call in the iteration."""
        iteration = Iteration(
            number=1,
            thought="thinking",
            cost_usd=0.01,
            tool_calls=[
                ToolCall(
                    tool_name="shell_exec",
                    tool_input={"command": "echo hi"},
                    tool_output="hi\n",
                    success=True,
                ),
                ToolCall(
                    tool_name="read_file",
                    tool_input={"path": "README.md"},
                    tool_output="# Title",
                    success=True,
                ),
            ],
        )

        await insert_tool_audit_logs(mock_pool, session, iteration)

        mock_pool.executemany.assert_called_once()
        args = mock_pool.executemany.call_args
        sql = args[0][0]
        rows = args[0][1]

        assert "tool_audit_log" in sql
        assert len(rows) == 2
        assert rows[0][1] == "shell_exec"
        assert rows[1][1] == "read_file"

    @pytest.mark.asyncio
    async def test_skips_empty_tool_calls(self, mock_pool, session):
        """Should skip if no tool calls in the iteration."""
        iteration = Iteration(
            number=1,
            thought="no tools",
            cost_usd=0.01,
            tool_calls=[],
        )

        await insert_tool_audit_logs(mock_pool, session, iteration)

        mock_pool.executemany.assert_not_called()

    @pytest.mark.asyncio
    async def test_truncates_long_output(self, mock_pool, session):
        """Should truncate tool output to 2000 chars."""
        long_output = "x" * 5000
        iteration = Iteration(
            number=1,
            thought="big output",
            cost_usd=0.01,
            tool_calls=[
                ToolCall(
                    tool_name="shell_exec",
                    tool_input={"command": "cat bigfile"},
                    tool_output=long_output,
                    success=True,
                ),
            ],
        )

        await insert_tool_audit_logs(mock_pool, session, iteration)

        rows = mock_pool.executemany.call_args[0][1]
        assert len(rows[0][3]) == 2000

    @pytest.mark.asyncio
    async def test_error_fields(self, mock_pool, session):
        """Should pass error_message and success=False for failed tools."""
        iteration = Iteration(
            number=1,
            thought="error case",
            cost_usd=0.01,
            tool_calls=[
                ToolCall(
                    tool_name="shell_exec",
                    tool_input={"command": "rm -rf /"},
                    tool_output="",
                    success=False,
                    error_message="Error: command blocked by sandbox",
                    duration_ms=5,
                ),
            ],
        )

        await insert_tool_audit_logs(mock_pool, session, iteration)

        rows = mock_pool.executemany.call_args[0][1]
        assert rows[0][4] is False  # success
        assert "blocked" in rows[0][5]  # error_message
        assert rows[0][6] == 5  # duration_ms

    @pytest.mark.asyncio
    async def test_session_id_passed(self, mock_pool, session):
        """Should pass the session ID to each row."""
        iteration = Iteration(
            number=1,
            thought="test",
            cost_usd=0.01,
            tool_calls=[
                ToolCall(
                    tool_name="read_file",
                    tool_input={"path": "."},
                    tool_output="data",
                    success=True,
                ),
            ],
        )

        await insert_tool_audit_logs(mock_pool, session, iteration)

        rows = mock_pool.executemany.call_args[0][1]
        assert rows[0][0] == session.id
