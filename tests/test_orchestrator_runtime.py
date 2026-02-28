"""Tests for mantis/orchestrator/runtime.py — OrchestratorRuntime."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from silkroute.mantis.orchestrator.decomposer import KeywordDecomposer, SingleTaskDecomposer
from silkroute.mantis.orchestrator.runtime import OrchestratorRuntime
from silkroute.mantis.runtime.interface import AgentResult, RuntimeConfig, RuntimeType


def _mock_child_factory(runtime_type: str | None = None):
    """Create a mock runtime that returns a fixed AgentResult."""
    mock_runtime = AsyncMock()
    mock_runtime.name = "mock"
    mock_runtime.invoke.return_value = AgentResult(
        status="completed",
        output="Task done",
        iterations=2,
        cost_usd=0.05,
    )
    return mock_runtime


class TestOrchestratorRuntime:
    """Full-flow orchestrator tests with mock child runtimes."""

    @pytest.mark.asyncio
    async def test_single_task_passthrough(self):
        """Single-task decomposition should invoke once and return."""
        runtime = OrchestratorRuntime(
            decomposer=SingleTaskDecomposer(),
            child_factory=_mock_child_factory,
        )

        result = await runtime.invoke("fix the login bug")

        assert result.status == "completed"
        assert result.output == "Task done"
        assert result.iterations == 2
        assert result.metadata["orchestrated"] is True
        assert result.metadata["sub_task_count"] == 1

    @pytest.mark.asyncio
    async def test_compound_task_multiple_subtasks(self):
        """Compound task should decompose into multiple sub-tasks."""
        runtime = OrchestratorRuntime(
            decomposer=KeywordDecomposer(),
            child_factory=_mock_child_factory,
        )

        result = await runtime.invoke("review the code and write tests")

        assert result.status == "completed"
        assert result.metadata["sub_task_count"] == 2
        assert result.iterations == 4  # 2 iterations per sub-task

    @pytest.mark.asyncio
    async def test_sequential_tasks_multiple_stages(self):
        """'and then' tasks should execute in sequential stages."""
        runtime = OrchestratorRuntime(
            decomposer=KeywordDecomposer(),
            child_factory=_mock_child_factory,
        )

        result = await runtime.invoke("review the code and then write tests")

        assert result.status == "completed"
        assert result.metadata["stage_count"] == 2

    @pytest.mark.asyncio
    async def test_budget_tracking(self):
        """Budget should be tracked across sub-tasks."""
        runtime = OrchestratorRuntime(
            decomposer=KeywordDecomposer(),
            child_factory=_mock_child_factory,
        )

        result = await runtime.invoke(
            "review code and write tests",
            RuntimeConfig(budget_limit_usd=5.0),
        )

        assert result.cost_usd == pytest.approx(0.10)  # 2 * 0.05

    @pytest.mark.asyncio
    async def test_max_sub_tasks_cap(self):
        """Sub-tasks should be capped at max_sub_tasks."""
        runtime = OrchestratorRuntime(
            decomposer=KeywordDecomposer(),
            child_factory=_mock_child_factory,
            max_sub_tasks=2,
        )

        result = await runtime.invoke(
            "1. review code 2. write tests 3. deploy 4. notify"
        )

        # Should only execute 2 sub-tasks despite 4 being decomposed
        assert result.metadata["sub_task_count"] == 2

    @pytest.mark.asyncio
    async def test_child_failure_isolated(self):
        """One failing child should not crash the orchestrator."""
        call_count = 0

        def factory(rt=None):
            nonlocal call_count
            call_count += 1
            mock = AsyncMock()
            mock.name = "mock"
            if call_count == 1:
                mock.invoke.return_value = AgentResult(
                    status="failed", error="LLM error", cost_usd=0.01
                )
            else:
                mock.invoke.return_value = AgentResult(
                    status="completed", output="Done", cost_usd=0.02
                )
            return mock

        runtime = OrchestratorRuntime(
            decomposer=KeywordDecomposer(),
            child_factory=factory,
        )

        result = await runtime.invoke("review code and write tests")

        assert result.status == "partial_failure"

    @pytest.mark.asyncio
    async def test_child_exception_captured(self):
        """Child runtime exception should be captured, not propagated."""
        def factory(rt=None):
            mock = AsyncMock()
            mock.name = "mock"
            mock.invoke.side_effect = RuntimeError("Connection refused")
            return mock

        runtime = OrchestratorRuntime(
            decomposer=SingleTaskDecomposer(),
            child_factory=factory,
        )

        result = await runtime.invoke("do something")

        assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_name_property(self):
        runtime = OrchestratorRuntime()
        assert runtime.name == "orchestrator"

    @pytest.mark.asyncio
    async def test_config_propagation(self):
        """Config values should flow to child runtimes."""
        captured_configs = []

        def factory(rt=None):
            mock = AsyncMock()
            mock.name = "mock"

            async def capture_invoke(task, config=None):
                captured_configs.append(config)
                return AgentResult(status="completed", output="ok", cost_usd=0.01)

            mock.invoke = capture_invoke
            return mock

        runtime = OrchestratorRuntime(
            decomposer=SingleTaskDecomposer(),
            child_factory=factory,
        )

        await runtime.invoke(
            "fix bugs",
            RuntimeConfig(budget_limit_usd=3.0, max_iterations=10),
        )

        assert len(captured_configs) == 1
        assert captured_configs[0].max_iterations == 10


class TestOrchestratorStream:
    """Orchestrator streaming tests."""

    @pytest.mark.asyncio
    async def test_stream_yields_stage_markers(self):
        """Stream should yield stage_start events."""
        import json

        runtime = OrchestratorRuntime(
            decomposer=KeywordDecomposer(),
            child_factory=_mock_child_factory,
        )

        chunks = []
        async for chunk in runtime.stream("review code and write tests"):
            chunks.append(json.loads(chunk))

        types = [c["type"] for c in chunks]
        assert "stage_start" in types
        assert "sub_task_completed" in types

    @pytest.mark.asyncio
    async def test_stream_error_handling(self):
        """Stream should yield error events for failing sub-tasks."""
        import json

        def factory(rt=None):
            mock = AsyncMock()
            mock.name = "mock"
            mock.invoke.side_effect = RuntimeError("boom")
            return mock

        runtime = OrchestratorRuntime(
            decomposer=SingleTaskDecomposer(),
            child_factory=factory,
        )

        chunks = []
        async for chunk in runtime.stream("failing task"):
            chunks.append(json.loads(chunk))

        types = [c["type"] for c in chunks]
        assert "sub_task_error" in types


class TestRegistryIntegration:
    """OrchestratorRuntime integration with registry."""

    def test_registry_creates_orchestrator(self):
        from silkroute.mantis.runtime.registry import get_runtime, reset_runtime

        reset_runtime()
        runtime = get_runtime(RuntimeType.ORCHESTRATOR)
        assert runtime.name == "orchestrator"
        reset_runtime()

    def test_registry_unknown_type_error(self):
        from silkroute.mantis.runtime.registry import get_runtime, reset_runtime

        reset_runtime()
        with pytest.raises(ValueError, match="Unknown runtime"):
            get_runtime("nonexistent")
        reset_runtime()
