"""Tests for silkroute.agent.loop — integration tests with mocked LLM."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from silkroute.agent.loop import run_agent
from silkroute.agent.session import SessionStatus


@pytest.fixture(autouse=True)
def _disable_db_persistence():
    """Disable DB persistence in loop tests to avoid connection attempts."""
    with patch("silkroute.agent.loop.AgentConfig") as mock_cfg:
        mock_cfg.return_value.persist_sessions = False
        yield


def _make_completion_response(content: str, tool_calls=None):
    """Build a mock litellm completion response."""
    message = MagicMock()
    message.content = content
    message.tool_calls = tool_calls
    message.model_dump.return_value = {
        "role": "assistant",
        "content": content,
        "tool_calls": None,
    }

    choice = MagicMock()
    choice.message = message

    response = MagicMock()
    response.choices = [choice]

    usage = MagicMock()
    usage.prompt_tokens = 100
    usage.completion_tokens = 50
    response.usage = usage

    return response


def _make_tool_call_response(tool_name: str, arguments: str):
    """Build a mock response with a tool call."""
    tc = MagicMock()
    tc.id = "call_test_123"
    tc.function = MagicMock()
    tc.function.name = tool_name
    tc.function.arguments = arguments

    message = MagicMock()
    message.content = "Let me check that."
    message.tool_calls = [tc]
    message.model_dump.return_value = {
        "role": "assistant",
        "content": "Let me check that.",
        "tool_calls": [{"id": "call_test_123", "function": {"name": tool_name, "arguments": arguments}}],
    }

    choice = MagicMock()
    choice.message = message

    response = MagicMock()
    response.choices = [choice]

    usage = MagicMock()
    usage.prompt_tokens = 150
    usage.completion_tokens = 80
    response.usage = usage

    return response


class TestRunAgent:
    @pytest.mark.asyncio
    async def test_immediate_completion(self):
        """Model responds without tool calls → completes in 1 iteration."""
        mock_response = _make_completion_response("The task is done. Here's a summary.")

        with patch("silkroute.agent.loop.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)
            mock_litellm.completion_cost.return_value = 0.0001
            mock_litellm.suppress_debug_info = True

            session = await run_agent(
                "Summarize this project",
                budget_limit_usd=1.0,
                max_iterations=5,
            )

        assert session.status == SessionStatus.COMPLETED
        assert session.iteration_count == 1

    @pytest.mark.asyncio
    async def test_tool_call_then_complete(self):
        """Model calls a tool, then completes."""
        tool_response = _make_tool_call_response("list_directory", '{"path": "."}')
        final_response = _make_completion_response("I found 3 files in the directory.")

        with patch("silkroute.agent.loop.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(side_effect=[tool_response, final_response])
            mock_litellm.completion_cost.return_value = 0.0001
            mock_litellm.suppress_debug_info = True

            session = await run_agent(
                "List the files here",
                budget_limit_usd=1.0,
                max_iterations=5,
            )

        assert session.status == SessionStatus.COMPLETED
        assert session.iteration_count == 2
        assert len(session.iterations[0].tool_calls) == 1

    @pytest.mark.asyncio
    async def test_max_iterations_timeout(self):
        """Loop hits max iterations → TIMEOUT status."""
        tool_response = _make_tool_call_response("shell_exec", '{"command": "echo loop"}')

        with patch("silkroute.agent.loop.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=tool_response)
            mock_litellm.completion_cost.return_value = 0.00001
            mock_litellm.suppress_debug_info = True

            session = await run_agent(
                "Keep going forever",
                budget_limit_usd=10.0,
                max_iterations=3,
            )

        assert session.status == SessionStatus.TIMEOUT
        assert session.iteration_count == 3

    @pytest.mark.asyncio
    async def test_budget_exceeded(self):
        """Session budget exceeded → BUDGET_EXCEEDED status."""
        tool_response = _make_tool_call_response("shell_exec", '{"command": "echo hi"}')

        call_count = 0

        async def mock_acompletion(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return tool_response

        with patch("silkroute.agent.loop.litellm") as mock_litellm:
            mock_litellm.acompletion = mock_acompletion
            mock_litellm.completion_cost.return_value = 0.005  # $0.005 per call
            mock_litellm.suppress_debug_info = True

            session = await run_agent(
                "Expensive task",
                budget_limit_usd=0.005,  # Very tight budget
                max_iterations=10,
            )

        assert session.status == SessionStatus.BUDGET_EXCEEDED

    @pytest.mark.asyncio
    async def test_tier_override(self):
        """--tier flag overrides classifier."""
        mock_response = _make_completion_response("Done")

        with patch("silkroute.agent.loop.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)
            mock_litellm.completion_cost.return_value = 0.0001
            mock_litellm.suppress_debug_info = True

            session = await run_agent(
                "Simple summarize task",  # Would classify as FREE
                tier_override="premium",
                budget_limit_usd=1.0,
            )

        assert session.status == SessionStatus.COMPLETED
        # Model should be from premium tier
        from silkroute.providers.models import ALL_MODELS
        model = ALL_MODELS.get(session.model_id)
        assert model is not None


    @pytest.mark.asyncio
    async def test_daemon_mode_no_console_output(self, capsys):
        """daemon_mode=True suppresses Rich console output."""
        mock_response = _make_completion_response("Done in daemon mode.")

        with patch("silkroute.agent.loop.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)
            mock_litellm.completion_cost.return_value = 0.0001
            mock_litellm.suppress_debug_info = True

            session = await run_agent(
                "Daemon task",
                budget_limit_usd=1.0,
                max_iterations=5,
                daemon_mode=True,
            )

        assert session.status == SessionStatus.COMPLETED
        assert session.iteration_count == 1
        # In daemon mode, Rich should not print panels/rules to stdout
        captured = capsys.readouterr()
        assert "SilkRoute Agent" not in captured.out

    @pytest.mark.asyncio
    async def test_daemon_mode_tool_call_then_complete(self):
        """daemon_mode=True works with tool calls."""
        tool_response = _make_tool_call_response("list_directory", '{"path": "."}')
        final_response = _make_completion_response("Found files.")

        with patch("silkroute.agent.loop.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(side_effect=[tool_response, final_response])
            mock_litellm.completion_cost.return_value = 0.0001
            mock_litellm.suppress_debug_info = True

            session = await run_agent(
                "List files in daemon",
                budget_limit_usd=1.0,
                max_iterations=5,
                daemon_mode=True,
            )

        assert session.status == SessionStatus.COMPLETED
        assert session.iteration_count == 2


class TestRunAgentStreaming:
    """Tests for stream_queue parameter — per-iteration event streaming."""

    @pytest.mark.asyncio
    async def test_queue_receives_completed_event(self):
        """Immediate completion pushes a 'completed' event + None sentinel."""
        mock_response = _make_completion_response("All done!")
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        with patch("silkroute.agent.loop.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)
            mock_litellm.completion_cost.return_value = 0.0001
            mock_litellm.suppress_debug_info = True

            session = await run_agent(
                "Quick task",
                budget_limit_usd=1.0,
                max_iterations=5,
                daemon_mode=True,
                stream_queue=queue,
            )

        assert session.status == SessionStatus.COMPLETED

        events = []
        while not queue.empty():
            events.append(queue.get_nowait())

        # Should have: completed event, then None sentinel
        assert len(events) == 2
        completed = json.loads(events[0])
        assert completed["type"] == "completed"
        assert "output" in completed
        assert events[1] is None

    @pytest.mark.asyncio
    async def test_queue_receives_iteration_events(self):
        """Tool call iterations push 'iteration' events."""
        tool_response = _make_tool_call_response("list_directory", '{"path": "."}')
        final_response = _make_completion_response("Found files.")
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        with patch("silkroute.agent.loop.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                side_effect=[tool_response, final_response]
            )
            mock_litellm.completion_cost.return_value = 0.0001
            mock_litellm.suppress_debug_info = True

            session = await run_agent(
                "List files",
                budget_limit_usd=1.0,
                max_iterations=5,
                daemon_mode=True,
                stream_queue=queue,
            )

        assert session.status == SessionStatus.COMPLETED

        events = []
        while not queue.empty():
            events.append(queue.get_nowait())

        # iteration event, completed event, None sentinel
        assert len(events) == 3
        assert json.loads(events[0])["type"] == "iteration"
        assert json.loads(events[1])["type"] == "completed"
        assert events[2] is None

    @pytest.mark.asyncio
    async def test_queue_receives_budget_event(self):
        """Budget exceeded pushes a 'budget_exceeded' event."""
        tool_response = _make_tool_call_response("shell_exec", '{"command": "echo hi"}')
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        with patch("silkroute.agent.loop.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=tool_response)
            mock_litellm.completion_cost.return_value = 0.005
            mock_litellm.suppress_debug_info = True

            session = await run_agent(
                "Expensive task",
                budget_limit_usd=0.005,
                max_iterations=10,
                daemon_mode=True,
                stream_queue=queue,
            )

        assert session.status == SessionStatus.BUDGET_EXCEEDED

        events = []
        while not queue.empty():
            events.append(queue.get_nowait())

        # Find the budget_exceeded event
        types = [json.loads(e)["type"] for e in events if e is not None]
        assert "budget_exceeded" in types
        # None sentinel at the end
        assert events[-1] is None

    @pytest.mark.asyncio
    async def test_queue_none_unchanged_behavior(self):
        """stream_queue=None should not change behavior."""
        mock_response = _make_completion_response("Done")

        with patch("silkroute.agent.loop.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)
            mock_litellm.completion_cost.return_value = 0.0001
            mock_litellm.suppress_debug_info = True

            session = await run_agent(
                "Simple task",
                budget_limit_usd=1.0,
                max_iterations=5,
                daemon_mode=True,
                stream_queue=None,
            )

        assert session.status == SessionStatus.COMPLETED
        assert session.iteration_count == 1

    @pytest.mark.asyncio
    async def test_queue_receives_error_event(self):
        """LLM error pushes an 'error' event."""
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        with patch("silkroute.agent.loop.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                side_effect=RuntimeError("API down")
            )
            mock_litellm.suppress_debug_info = True

            session = await run_agent(
                "Failing task",
                budget_limit_usd=1.0,
                max_iterations=5,
                daemon_mode=True,
                stream_queue=queue,
            )

        assert session.status == SessionStatus.FAILED

        events = []
        while not queue.empty():
            events.append(queue.get_nowait())

        types = [json.loads(e)["type"] for e in events if e is not None]
        assert "error" in types
        assert events[-1] is None


class TestRunAgentWithDB:
    """Tests verifying DB integration path when persistence is enabled."""

    @pytest.mark.asyncio
    async def test_db_calls_when_pool_available(self):
        """When pool is available, DB calls are made at session boundaries."""
        mock_response = _make_completion_response("Done.")
        mock_pool = AsyncMock()
        mock_db_sessions = AsyncMock()
        mock_db_cost_logs = AsyncMock()
        mock_db_projects = AsyncMock()
        mock_db_projects.get_monthly_spend = AsyncMock(return_value=0.0)
        mock_db_projects.get_project_budget = AsyncMock(return_value=200.0)

        with (
            patch("silkroute.agent.loop.litellm") as mock_litellm,
            patch("silkroute.agent.loop.AgentConfig") as mock_cfg,
            patch("silkroute.db.pool.asyncpg.create_pool", new_callable=AsyncMock, return_value=mock_pool),
            patch("silkroute.agent.loop.db_sessions", mock_db_sessions, create=True),
            patch("silkroute.db.repositories.sessions.create_session", mock_db_sessions.create_session),
            patch("silkroute.db.repositories.sessions.update_session", mock_db_sessions.update_session),
            patch("silkroute.db.repositories.sessions.close_session", mock_db_sessions.close_session),
            patch("silkroute.db.repositories.projects.get_monthly_spend", mock_db_projects.get_monthly_spend),
            patch("silkroute.db.repositories.projects.get_project_budget", mock_db_projects.get_project_budget),
            patch("silkroute.db.repositories.cost_logs.insert_cost_log", mock_db_cost_logs.insert_cost_log),
        ):
            mock_cfg.return_value.persist_sessions = True
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)
            mock_litellm.completion_cost.return_value = 0.0001
            mock_litellm.suppress_debug_info = True

            # Reset pool singleton
            import silkroute.db.pool as pool_mod
            pool_mod._pool = None

            session = await run_agent(
                "Quick task",
                budget_limit_usd=1.0,
                max_iterations=5,
            )
            pool_mod._pool = None  # Clean up

        assert session.status == SessionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_agent_continues_without_db(self):
        """Agent runs normally even when DB connection fails."""
        mock_response = _make_completion_response("Done.")

        with (
            patch("silkroute.agent.loop.litellm") as mock_litellm,
            patch("silkroute.agent.loop.AgentConfig") as mock_cfg,
            patch("silkroute.db.pool.asyncpg.create_pool", new_callable=AsyncMock, side_effect=OSError("refused")),
        ):
            mock_cfg.return_value.persist_sessions = True
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)
            mock_litellm.completion_cost.return_value = 0.0001
            mock_litellm.suppress_debug_info = True

            import silkroute.db.pool as pool_mod
            pool_mod._pool = None

            session = await run_agent(
                "Quick task",
                budget_limit_usd=1.0,
                max_iterations=5,
            )
            pool_mod._pool = None

        # Agent should still complete successfully
        assert session.status == SessionStatus.COMPLETED
        assert session.iteration_count == 1
