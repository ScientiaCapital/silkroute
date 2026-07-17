"""Security-gate tests: production fail-fast on empty auth + demo-mode cap.

These cover the Phase 0 hardening that makes SilkRoute safe to expose publicly:
- create_app() refuses to start in production without an API key.
- demo_mode disables the money-spending endpoints (/runtime/invoke,
  /runtime/stream, POST /tasks) while leaving read endpoints reachable.
"""

from __future__ import annotations

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient

from silkroute.api.app import create_app
from silkroute.api.deps import get_redis
from silkroute.config.settings import (
    ApiConfig,
    DatabaseConfig,
    ProviderConfig,
    SilkRouteSettings,
)
from silkroute.daemon.queue import TaskQueue

AUTH = {"Authorization": "Bearer test-secret"}


def _make_settings(*, environment: str = "development", demo_mode: bool = False) -> SilkRouteSettings:
    return SilkRouteSettings(
        environment=environment,
        providers=ProviderConfig(ollama_enabled=True),
        api=ApiConfig(api_key="test-secret", demo_mode=demo_mode),
        database=DatabaseConfig(
            redis_url="redis://localhost:6379/0",
            postgres_url="postgresql://silkroute:silkroute@localhost:5432/silkroute",
        ),
    )


def _wire_app(settings: SilkRouteSettings) -> TestClient:
    application = create_app(settings=settings)
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    application.state.redis = fake_redis
    application.state.queue = TaskQueue(fake_redis, maxsize=100)
    application.state.db_pool = None
    application.dependency_overrides[get_redis] = lambda: fake_redis
    return TestClient(application, raise_server_exceptions=False)


class TestProductionFailFast:
    """create_app() must refuse to start unauthenticated in production."""

    def test_production_without_key_raises(self) -> None:
        settings = SilkRouteSettings(
            environment="production",
            providers=ProviderConfig(ollama_enabled=True),
            api=ApiConfig(api_key=""),
        )
        with pytest.raises(RuntimeError, match="production"):
            create_app(settings=settings)

    def test_production_with_key_starts(self) -> None:
        settings = SilkRouteSettings(
            environment="production",
            providers=ProviderConfig(ollama_enabled=True),
            api=ApiConfig(api_key="a-real-key"),
        )
        app = create_app(settings=settings)
        assert app is not None

    def test_development_without_key_starts(self) -> None:
        """Dev mode keeps the empty-key convenience."""
        settings = SilkRouteSettings(
            environment="development",
            providers=ProviderConfig(ollama_enabled=True),
            api=ApiConfig(api_key=""),
        )
        app = create_app(settings=settings)
        assert app is not None


class TestApiKeyEnvVar:
    """The documented SILKROUTE_API_KEY env var must actually enable auth."""

    def test_silkroute_api_key_populates_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SILKROUTE_OLLAMA_ENABLED", "true")
        monkeypatch.setenv("SILKROUTE_API_KEY", "documented-name-works")
        from silkroute.config.settings import load_settings

        assert load_settings().api.api_key == "documented-name-works"


class TestDemoModeCap:
    """demo_mode blocks money-spending endpoints, keeps reads open."""

    def test_invoke_blocked_in_demo_mode(self) -> None:
        app = _wire_app(_make_settings(demo_mode=True))
        resp = app.post("/runtime/invoke", json={"task": "spend money"}, headers=AUTH)
        assert resp.status_code == 403

    def test_stream_blocked_in_demo_mode(self) -> None:
        app = _wire_app(_make_settings(demo_mode=True))
        resp = app.get("/runtime/stream?task=spend", headers=AUTH)
        assert resp.status_code == 403

    def test_task_submit_blocked_in_demo_mode(self) -> None:
        app = _wire_app(_make_settings(demo_mode=True))
        resp = app.post("/tasks", json={"task": "spend money"}, headers=AUTH)
        assert resp.status_code == 403

    def test_queue_status_allowed_in_demo_mode(self) -> None:
        """Read-only queue status stays reachable under demo mode."""
        app = _wire_app(_make_settings(demo_mode=True))
        resp = app.get("/tasks/queue/status", headers=AUTH)
        assert resp.status_code == 200

    def test_budget_allowed_in_demo_mode(self) -> None:
        """Read-only budget stays reachable under demo mode."""
        app = _wire_app(_make_settings(demo_mode=True))
        resp = app.get("/budget", headers=AUTH)
        assert resp.status_code == 200

    def test_task_submit_allowed_when_not_demo(self) -> None:
        app = _wire_app(_make_settings(demo_mode=False))
        resp = app.post("/tasks", json={"task": "hello"}, headers=AUTH)
        assert resp.status_code == 201
