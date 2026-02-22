"""Tests for daemon serialization — JSON round-trip for task dataclasses."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from silkroute.daemon.queue import TaskRequest, TaskResult
from silkroute.daemon.serialization import (
    TaskEncoder,
    deserialize_request,
    deserialize_result,
    serialize_request,
    serialize_result,
)


class TestTaskEncoder:
    """TaskEncoder JSON encoder tests."""

    def test_encodes_datetime(self) -> None:
        dt = datetime(2026, 2, 22, 3, 0, 0, tzinfo=UTC)
        result = json.dumps({"ts": dt}, cls=TaskEncoder)
        assert "2026-02-22T03:00:00" in result

    def test_raises_for_unknown_types(self) -> None:
        with pytest.raises(TypeError):
            json.dumps({"bad": object()}, cls=TaskEncoder)


class TestSerializeRequest:
    """TaskRequest serialization tests."""

    def test_round_trip(self) -> None:
        original = TaskRequest(
            task="review code",
            project_id="myproject",
            model_override="deepseek/deepseek-r1-0528",
            tier_override="premium",
            max_iterations=50,
            budget_limit_usd=25.0,
            priority=3,
        )
        serialized = serialize_request(original)
        restored = deserialize_request(serialized)

        assert restored.task == original.task
        assert restored.id == original.id
        assert restored.project_id == original.project_id
        assert restored.model_override == original.model_override
        assert restored.tier_override == original.tier_override
        assert restored.max_iterations == original.max_iterations
        assert restored.budget_limit_usd == original.budget_limit_usd
        assert restored.priority == original.priority
        assert restored.submitted_at == original.submitted_at

    def test_round_trip_defaults(self) -> None:
        original = TaskRequest(task="simple")
        restored = deserialize_request(serialize_request(original))

        assert restored.task == "simple"
        assert restored.project_id == "default"
        assert restored.model_override is None
        assert restored.tier_override is None

    def test_serialized_is_valid_json(self) -> None:
        req = TaskRequest(task="test")
        data = json.loads(serialize_request(req))
        assert data["task"] == "test"
        assert "submitted_at" in data

    def test_preserves_datetime_precision(self) -> None:
        original = TaskRequest(task="test")
        restored = deserialize_request(serialize_request(original))
        # datetime.fromisoformat preserves microseconds
        assert abs((restored.submitted_at - original.submitted_at).total_seconds()) < 0.001


class TestSerializeResult:
    """TaskResult serialization tests."""

    def test_round_trip_success(self) -> None:
        original = TaskResult(
            request_id="abc-123",
            session_id="sess-456",
            status="completed",
            cost_usd=0.05,
            iterations=3,
            duration_ms=12000,
        )
        restored = deserialize_result(serialize_result(original))

        assert restored.request_id == original.request_id
        assert restored.session_id == original.session_id
        assert restored.status == original.status
        assert restored.cost_usd == original.cost_usd
        assert restored.iterations == original.iterations
        assert restored.duration_ms == original.duration_ms
        assert restored.error is None

    def test_round_trip_failure(self) -> None:
        original = TaskResult(
            request_id="abc-123",
            session_id="sess-456",
            status="failed",
            cost_usd=0.01,
            iterations=1,
            duration_ms=500,
            error="LLM API timeout",
        )
        restored = deserialize_result(serialize_result(original))

        assert restored.status == "failed"
        assert restored.error == "LLM API timeout"

    def test_serialized_is_valid_json(self) -> None:
        result = TaskResult(
            request_id="r1", session_id="s1", status="completed",
            cost_usd=0.02, iterations=2, duration_ms=5000,
        )
        data = json.loads(serialize_result(result))
        assert data["request_id"] == "r1"
        assert data["status"] == "completed"
