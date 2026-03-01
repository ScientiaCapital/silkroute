"""Tests for /runtime, /models, and /budget endpoints."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient

from silkroute.api.app import create_app
from silkroute.api.deps import get_redis
from silkroute.config.settings import SilkRouteSettings
from silkroute.daemon.queue import TaskQueue
from silkroute.mantis.runtime.interface import AgentResult


@pytest.fixture
def fake_redis_client() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def app(
    test_settings: SilkRouteSettings,
    fake_redis_client: fakeredis.aioredis.FakeRedis,
) -> TestClient:
    application = create_app(settings=test_settings)

    queue = TaskQueue(fake_redis_client, maxsize=100)
    application.state.redis = fake_redis_client
    application.state.queue = queue
    application.state.db_pool = None

    application.dependency_overrides[get_redis] = lambda: fake_redis_client

    return TestClient(application, raise_server_exceptions=False)


AUTH = {"Authorization": "Bearer test-secret"}


# --- Runtime endpoints ---


class TestRuntimeInvoke:
    """POST /runtime/invoke."""

    def test_invoke_returns_result(self, app: TestClient) -> None:
        mock_result = AgentResult(
            status="completed",
            session_id="sess-456",
            output="Hello from the agent",
            iterations=2,
            cost_usd=0.01,
        )
        mock_runtime = AsyncMock()
        mock_runtime.invoke.return_value = mock_result

        with patch(
            "silkroute.api.routes.runtime.get_runtime",
            return_value=mock_runtime,
        ):
            resp = app.post(
                "/runtime/invoke",
                json={"task": "say hello"},
                headers=AUTH,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["output"] == "Hello from the agent"
        assert data["session_id"] == "sess-456"

    def test_invoke_requires_auth(self, app: TestClient) -> None:
        resp = app.post("/runtime/invoke", json={"task": "hello"})
        assert resp.status_code == 401

    def test_invoke_empty_task(self, app: TestClient) -> None:
        resp = app.post("/runtime/invoke", json={"task": ""}, headers=AUTH)
        assert resp.status_code == 422


class TestRuntimeStream:
    """GET /runtime/stream (SSE)."""

    def test_stream_returns_event_stream(self, app: TestClient) -> None:
        async def mock_stream(task, config=None):
            yield "chunk1"
            yield "chunk2"

        mock_runtime = AsyncMock()
        mock_runtime.stream = mock_stream

        with patch(
            "silkroute.api.routes.runtime.get_runtime",
            return_value=mock_runtime,
        ):
            resp = app.get("/runtime/stream?task=hello", headers=AUTH)

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        assert "data: chunk1" in resp.text
        assert "data: chunk2" in resp.text
        assert "data: [DONE]" in resp.text

    def test_stream_requires_auth(self, app: TestClient) -> None:
        resp = app.get("/runtime/stream?task=hello")
        assert resp.status_code == 401

    def test_stream_missing_task(self, app: TestClient) -> None:
        resp = app.get("/runtime/stream", headers=AUTH)
        assert resp.status_code == 422

    def test_stream_timeout_error(self, app: TestClient) -> None:
        async def mock_stream_timeout(
            task: str, config: str | None = None
        ) -> AsyncGenerator[str, None]:
            yield "partial"
            raise TimeoutError("timed out")

        mock_runtime = AsyncMock()
        mock_runtime.stream = mock_stream_timeout

        with patch(
            "silkroute.api.routes.runtime.get_runtime",
            return_value=mock_runtime,
        ):
            resp = app.get("/runtime/stream?task=hello", headers=AUTH)

        assert "data: [ERROR] Stream timed out" in resp.text
        assert "data: [DONE]" not in resp.text

    def test_stream_generic_exception(self, app: TestClient) -> None:
        async def mock_stream_error(
            task: str, config: str | None = None
        ) -> AsyncGenerator[str, None]:
            if True:
                raise ValueError("boom")
            yield  # unreachable but makes it an async generator

        mock_runtime = AsyncMock()
        mock_runtime.stream = mock_stream_error

        with patch(
            "silkroute.api.routes.runtime.get_runtime",
            return_value=mock_runtime,
        ):
            resp = app.get("/runtime/stream?task=hello", headers=AUTH)

        assert "data: [ERROR] boom" in resp.text
        assert "data: [DONE]" not in resp.text

    def test_stream_no_done_on_error(self, app: TestClient) -> None:
        async def mock_stream_raises(
            task: str, config: str | None = None
        ) -> AsyncGenerator[str, None]:
            yield "first"
            raise RuntimeError("unexpected failure")

        mock_runtime = AsyncMock()
        mock_runtime.stream = mock_stream_raises

        with patch(
            "silkroute.api.routes.runtime.get_runtime",
            return_value=mock_runtime,
        ):
            resp = app.get("/runtime/stream?task=hello", headers=AUTH)

        assert "[ERROR]" in resp.text
        assert "data: [DONE]" not in resp.text


# --- Model catalog ---


class TestModels:
    """GET /models and GET /models/{model_id}."""

    def test_list_all_models(self, app: TestClient) -> None:
        resp = app.get("/models")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 13  # 13 models in the registry

    def test_filter_by_tier(self, app: TestClient) -> None:
        resp = app.get("/models?tier=free")
        assert resp.status_code == 200
        data = resp.json()
        assert all(m["tier"] == "free" for m in data)

    def test_filter_by_capability(self, app: TestClient) -> None:
        resp = app.get("/models?capability=coding")
        assert resp.status_code == 200
        data = resp.json()
        assert all("coding" in m["capabilities"] for m in data)

    def test_invalid_tier(self, app: TestClient) -> None:
        resp = app.get("/models?tier=invalid")
        assert resp.status_code == 400

    def test_get_specific_model(self, app: TestClient) -> None:
        resp = app.get("/models/deepseek/deepseek-v3.2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["model_id"] == "deepseek/deepseek-v3.2"
        assert data["name"] == "DeepSeek V3.2"

    def test_model_not_found(self, app: TestClient) -> None:
        resp = app.get("/models/nonexistent/model")
        assert resp.status_code == 404

    def test_models_no_auth_required(self, app: TestClient) -> None:
        """Model catalog is public (no auth)."""
        resp = app.get("/models")
        assert resp.status_code == 200


# --- Budget ---


class TestBudget:
    """GET /budget and GET /budget/{project_id}."""

    def test_global_budget_without_db(self, app: TestClient) -> None:
        """Without Postgres, budget returns zeros (fail-open)."""
        resp = app.get("/budget", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert data["daily_spent_usd"] == 0.0
        assert data["monthly_spent_usd"] == 0.0
        assert data["allowed"] is True
        assert data["daily_limit_usd"] == 10.0
        assert data["monthly_limit_usd"] == 200.0

    def test_project_budget_without_db(self, app: TestClient) -> None:
        resp = app.get("/budget/myproject", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == "myproject"
        assert data["monthly_spent_usd"] == 0.0
        assert data["daily_spent_usd"] == 0.0

    def test_budget_requires_auth(self, app: TestClient) -> None:
        resp = app.get("/budget")
        assert resp.status_code == 401

    def test_project_budget_requires_auth(self, app: TestClient) -> None:
        resp = app.get("/budget/myproject")
        assert resp.status_code == 401
