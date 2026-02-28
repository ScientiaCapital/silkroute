"""Tests for the Mantis runtime abstraction layer."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from silkroute.mantis.runtime.deepagents import DeepAgentsRuntime
from silkroute.mantis.runtime.interface import (
    AgentResult,
    AgentRuntime,
    RuntimeConfig,
    RuntimeType,
)
from silkroute.mantis.runtime.legacy import LegacyRuntime
from silkroute.mantis.runtime.registry import get_runtime, reset_runtime


class TestRuntimeConfig:
    """RuntimeConfig defaults and override."""

    def test_defaults(self) -> None:
        config = RuntimeConfig()
        assert config.runtime_type in (RuntimeType.LEGACY, RuntimeType.DEEP_AGENTS)
        assert config.workspace_dir == "."
        assert config.project_id == "default"
        assert config.max_iterations == 25
        assert config.budget_limit_usd == 10.0

    def test_override(self) -> None:
        config = RuntimeConfig(
            runtime_type=RuntimeType.DEEP_AGENTS,
            workspace_dir="/tmp/test",
            project_id="proj-1",
            model_override="deepseek/deepseek-v3.2",
            max_iterations=10,
            budget_limit_usd=5.0,
        )
        assert config.runtime_type == "deepagents"
        assert config.workspace_dir == "/tmp/test"

    def test_env_var_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SILKROUTE_RUNTIME", "deepagents")
        config = RuntimeConfig()
        assert config.runtime_type == "deepagents"


class TestAgentResult:
    """AgentResult dataclass."""

    def test_success_property(self) -> None:
        result = AgentResult(status="completed", output="done")
        assert result.success is True

    def test_failure_property(self) -> None:
        result = AgentResult(status="failed", error="something broke")
        assert result.success is False

    def test_all_statuses(self) -> None:
        for status in ("completed", "failed", "timeout", "budget_exceeded"):
            result = AgentResult(status=status)
            assert result.success == (status == "completed")


class TestAgentRuntimeProtocol:
    """Verify protocol compliance."""

    def test_legacy_satisfies_protocol(self) -> None:
        runtime = LegacyRuntime()
        assert isinstance(runtime, AgentRuntime)

    def test_deepagents_satisfies_protocol(self) -> None:
        runtime = DeepAgentsRuntime()
        assert isinstance(runtime, AgentRuntime)


class TestLegacyRuntime:
    """LegacyRuntime delegates to run_agent()."""

    @pytest.mark.asyncio
    async def test_invoke_delegates_to_run_agent(self) -> None:
        # Mock the entire run_agent function
        mock_session = MagicMock()
        mock_session.status.value = "completed"
        mock_session.id = "session-123"
        mock_session.iteration_count = 3
        mock_session.total_cost_usd = 0.05
        mock_session.model_id = "deepseek/deepseek-v3.2"
        mock_session.total_input_tokens = 5000
        mock_session.total_output_tokens = 2000
        mock_session.iterations = [
            MagicMock(thought="Final answer: done."),
        ]

        with patch("silkroute.agent.loop.run_agent", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_session

            runtime = LegacyRuntime()
            result = await runtime.invoke("Fix the bug")

        assert result.success is True
        assert result.session_id == "session-123"
        assert result.iterations == 3
        assert result.cost_usd == 0.05
        assert result.output == "Final answer: done."
        assert result.metadata["model_id"] == "deepseek/deepseek-v3.2"

        # Verify run_agent was called with correct args
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["daemon_mode"] is True

    @pytest.mark.asyncio
    async def test_invoke_with_config(self) -> None:
        mock_session = MagicMock()
        mock_session.status.value = "completed"
        mock_session.id = "s-1"
        mock_session.iteration_count = 1
        mock_session.total_cost_usd = 0.01
        mock_session.model_id = "test"
        mock_session.total_input_tokens = 100
        mock_session.total_output_tokens = 50
        mock_session.iterations = [MagicMock(thought="ok")]

        with patch("silkroute.agent.loop.run_agent", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_session

            runtime = LegacyRuntime()
            config = RuntimeConfig(
                project_id="proj-1",
                model_override="deepseek/deepseek-r1-0528",
                max_iterations=10,
                budget_limit_usd=5.0,
            )
            await runtime.invoke("Do task", config=config)

        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["project_id"] == "proj-1"
        assert call_kwargs["model_override"] == "deepseek/deepseek-r1-0528"
        assert call_kwargs["max_iterations"] == 10
        assert call_kwargs["budget_limit_usd"] == 5.0

    @pytest.mark.asyncio
    async def test_stream_yields_output(self) -> None:
        """stream() now uses asyncio.Queue — mock run_agent to push events."""
        import json

        async def mock_run_agent(task, *, stream_queue=None, **kwargs):
            """Mock that pushes a stream event and None sentinel."""
            if stream_queue is not None:
                await stream_queue.put(json.dumps({"type": "completed", "output": "streamed output"}))
                await stream_queue.put(None)
            mock_session = MagicMock()
            mock_session.status.value = "completed"
            mock_session.id = "s-1"
            return mock_session

        with patch("silkroute.agent.loop.run_agent", mock_run_agent):
            runtime = LegacyRuntime()
            chunks = []
            async for chunk in runtime.stream("Do task"):
                chunks.append(chunk)

        assert len(chunks) == 1
        parsed = json.loads(chunks[0])
        assert parsed["type"] == "completed"
        assert parsed["output"] == "streamed output"

    def test_name(self) -> None:
        assert LegacyRuntime().name == "legacy"


class TestDeepAgentsRuntime:
    """DeepAgentsRuntime delegates to code_writer."""

    @pytest.mark.asyncio
    async def test_invoke_without_deepagents_raises(self) -> None:
        """When deepagents is not importable, raise NotImplementedError."""
        runtime = DeepAgentsRuntime()
        with patch.dict("sys.modules", {"deepagents": None}):
            with pytest.raises(NotImplementedError, match="deepagents"):
                await runtime.invoke("Do task")

    @pytest.mark.asyncio
    async def test_invoke_delegates_to_code_writer(self) -> None:
        """When deepagents is available, delegates to run_code_writer."""
        from silkroute.mantis.agents.code_writer import CodeWriterResult

        mock_result = CodeWriterResult(
            status="completed",
            output="done",
            metadata={"runtime": "deepagents", "model": "deepseek/deepseek-v3.2"},
        )

        with patch(
            "silkroute.mantis.agents.code_writer.run_code_writer",
            return_value=mock_result,
        ) as mock_run:
            runtime = DeepAgentsRuntime()
            result = await runtime.invoke("Fix the bug")

        assert result.success is True
        assert result.output == "done"
        assert result.metadata["runtime"] == "deepagents"
        mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_stream_yields_output(self) -> None:
        """stream() uses batch-then-yield pattern."""
        from silkroute.mantis.agents.code_writer import CodeWriterResult

        mock_result = CodeWriterResult(
            status="completed",
            output="streamed output",
            metadata={"runtime": "deepagents", "model": "test"},
        )

        with patch(
            "silkroute.mantis.agents.code_writer.run_code_writer",
            return_value=mock_result,
        ):
            runtime = DeepAgentsRuntime()
            chunks = []
            async for chunk in runtime.stream("Do task"):
                chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0] == "streamed output"

    def test_name(self) -> None:
        assert DeepAgentsRuntime().name == "deepagents"


class TestRuntimeRegistry:
    """get_runtime() factory and caching."""

    def setup_method(self) -> None:
        reset_runtime()

    def teardown_method(self) -> None:
        reset_runtime()

    def test_default_is_legacy(self) -> None:
        runtime = get_runtime()
        assert isinstance(runtime, LegacyRuntime)

    def test_explicit_legacy(self) -> None:
        runtime = get_runtime("legacy")
        assert isinstance(runtime, LegacyRuntime)

    def test_explicit_deepagents(self) -> None:
        runtime = get_runtime("deepagents")
        assert isinstance(runtime, DeepAgentsRuntime)

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown runtime"):
            get_runtime("nonexistent")

    def test_caching(self) -> None:
        r1 = get_runtime("legacy")
        r2 = get_runtime("legacy")
        assert r1 is r2  # Same instance

    def test_type_change_creates_new(self) -> None:
        r1 = get_runtime("legacy")
        r2 = get_runtime("deepagents")
        assert r1 is not r2
        assert isinstance(r2, DeepAgentsRuntime)

    def test_env_var_selection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SILKROUTE_RUNTIME", "deepagents")
        reset_runtime()
        runtime = get_runtime()
        assert isinstance(runtime, DeepAgentsRuntime)

    def test_reset(self) -> None:
        get_runtime("legacy")
        reset_runtime()
        # After reset, a new instance should be created
        r = get_runtime("legacy")
        assert isinstance(r, LegacyRuntime)
