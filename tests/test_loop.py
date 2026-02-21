"""Tests for silkroute.agent.loop — integration tests with mocked LLM."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from silkroute.agent.loop import run_agent
from silkroute.agent.session import SessionStatus


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
