"""Tests for /tasks endpoints — submit, poll, queue status."""

from __future__ import annotations

import pytest
import fakeredis.aioredis
from fastapi.testclient import TestClient

from silkroute.api.app import create_app
from silkroute.api.deps import get_redis
from silkroute.config.settings import (
    ApiConfig,
    DatabaseConfig,
    ProviderConfig,
    SilkRouteSettings,
)
from silkroute.daemon.queue import TaskQueue, TaskResult


@pytest.fixture
def test_settings() -> SilkRouteSettings:
    return SilkRouteSettings(
        providers=ProviderConfig(ollama_enabled=True),
        api=ApiConfig(api_key="test-secret"),
        database=DatabaseConfig(
            redis_url="redis://localhost:6379/0",
            postgres_url="postgresql://silkroute:silkroute@localhost:5432/silkroute",
        ),
    )


@pytest.fixture
def fake_redis_client() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def app(
    test_settings: SilkRouteSettings,
    fake_redis_client: fakeredis.aioredis.FakeRedis,
) -> TestClient:
    application = create_app(settings=test_settings)

    # Wire up fake Redis + queue
    queue = TaskQueue(fake_redis_client, maxsize=100)
    application.state.redis = fake_redis_client
    application.state.queue = queue
    application.state.db_pool = None

    # Override the DI so routes get the fake
    application.dependency_overrides[get_redis] = lambda: fake_redis_client

    return TestClient(application, raise_server_exceptions=False)


AUTH_HEADER = {"Authorization": "Bearer test-secret"}
BAD_AUTH = {"Authorization": "Bearer wrong-key"}


class TestAuth:
    """Authentication enforcement."""

    def test_missing_auth_returns_401(self, app: TestClient) -> None:
        resp = app.post("/tasks", json={"task": "hello"})
        assert resp.status_code == 401

    def test_bad_token_returns_401(self, app: TestClient) -> None:
        resp = app.post("/tasks", json={"task": "hello"}, headers=BAD_AUTH)
        assert resp.status_code == 401

    def test_valid_token_passes(self, app: TestClient) -> None:
        resp = app.post("/tasks", json={"task": "hello"}, headers=AUTH_HEADER)
        assert resp.status_code == 201

    def test_no_auth_when_key_empty(self, app: TestClient) -> None:
        """When API key is empty, auth is disabled (dev mode)."""
        app.app.state.settings.api.api_key = ""  # type: ignore[union-attr]
        resp = app.post("/tasks", json={"task": "hello"})
        assert resp.status_code == 201


class TestSubmitTask:
    """POST /tasks."""

    def test_submit_returns_task_id(self, app: TestClient) -> None:
        resp = app.post("/tasks", json={"task": "fix the bug"}, headers=AUTH_HEADER)
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["status"] == "queued"

    def test_submit_with_options(self, app: TestClient) -> None:
        resp = app.post(
            "/tasks",
            json={
                "task": "write tests",
                "project_id": "myproject",
                "tier_override": "premium",
                "max_iterations": 50,
                "budget_limit_usd": 5.0,
            },
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 201

    def test_submit_empty_task_fails(self, app: TestClient) -> None:
        resp = app.post("/tasks", json={"task": ""}, headers=AUTH_HEADER)
        assert resp.status_code == 422

    def test_submit_queue_full_returns_429(self, app: TestClient) -> None:
        """When the queue is at max capacity, return 429."""
        # Override queue with maxsize=1
        app.app.state.queue = TaskQueue(  # type: ignore[union-attr]
            app.app.state.redis,  # type: ignore[union-attr]
            maxsize=1,
        )
        # Fill it
        app.post("/tasks", json={"task": "task1"}, headers=AUTH_HEADER)
        # This should 429
        resp = app.post("/tasks", json={"task": "task2"}, headers=AUTH_HEADER)
        assert resp.status_code == 429


class TestQueueStatus:
    """GET /tasks/queue/status."""

    def test_empty_queue(self, app: TestClient) -> None:
        resp = app.get("/tasks/queue/status", headers=AUTH_HEADER)
        assert resp.status_code == 200
        data = resp.json()
        assert data["pending"] == 0
        assert data["total_submitted"] == 0
        assert data["total_completed"] == 0

    def test_after_submit(self, app: TestClient) -> None:
        app.post("/tasks", json={"task": "hello"}, headers=AUTH_HEADER)
        resp = app.get("/tasks/queue/status", headers=AUTH_HEADER)
        data = resp.json()
        assert data["pending"] == 1
        assert data["total_submitted"] == 1


class TestGetResult:
    """GET /tasks/{task_id}/result."""

    def test_missing_result_returns_404(self, app: TestClient) -> None:
        resp = app.get("/tasks/nonexistent/result", headers=AUTH_HEADER)
        assert resp.status_code == 404

    def test_completed_result(self, app: TestClient) -> None:
        """Submit a task, record a result, then poll for it."""
        # Submit
        resp = app.post("/tasks", json={"task": "hello"}, headers=AUTH_HEADER)
        task_id = resp.json()["id"]

        # Simulate worker recording a result by calling queue directly
        import asyncio

        queue: TaskQueue = app.app.state.queue  # type: ignore[union-attr]
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                queue.record_result(
                    TaskResult(
                        request_id=task_id,
                        session_id="sess-123",
                        status="completed",
                        cost_usd=0.05,
                        iterations=3,
                        duration_ms=1500,
                    )
                )
            )
        finally:
            loop.close()

        # Poll
        resp = app.get(f"/tasks/{task_id}/result", headers=AUTH_HEADER)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["session_id"] == "sess-123"
        assert data["cost_usd"] == 0.05
        assert data["iterations"] == 3


class TestRedisUnavailable:
    """503 when Redis is down."""

    def test_submit_without_redis_returns_503(self, app: TestClient) -> None:
        app.app.state.queue = None  # type: ignore[union-attr]
        resp = app.post("/tasks", json={"task": "hello"}, headers=AUTH_HEADER)
        assert resp.status_code == 503

    def test_queue_status_without_redis_returns_503(self, app: TestClient) -> None:
        app.app.state.queue = None  # type: ignore[union-attr]
        resp = app.get("/tasks/queue/status", headers=AUTH_HEADER)
        assert resp.status_code == 503
