"""Tests for /health and /health/ready endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from silkroute import __version__
from silkroute.api.app import create_app
from silkroute.config.settings import SilkRouteSettings


@pytest.fixture
def app(test_settings: SilkRouteSettings) -> TestClient:
    """Create a test app with no real Redis/DB connections.

    We override the lifespan-created state to avoid needing running services.
    """
    application = create_app(settings=test_settings)

    # Skip lifespan (no real Redis/DB) by setting state directly
    application.state.redis = None
    application.state.queue = None
    application.state.db_pool = None

    return TestClient(application, raise_server_exceptions=False)


class TestHealthEndpoint:
    """GET /health — liveness probe."""

    def test_returns_ok(self, app: TestClient) -> None:
        resp = app.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == __version__
        assert data["service"] == "silkroute-api"


class TestHealthReadyEndpoint:
    """GET /health/ready — readiness probe."""

    def test_degraded_without_services(self, app: TestClient) -> None:
        """When Redis and DB are unavailable, returns degraded status."""
        resp = app.get("/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["checks"]["redis"] == "unavailable"
        assert data["checks"]["postgres"] == "unavailable"

    def test_ready_with_redis(self, app: TestClient) -> None:
        """When Redis is available, redis check is ok."""
        import fakeredis.aioredis

        fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
        app.app.state.redis = fake  # type: ignore[union-attr]

        resp = app.get("/health/ready")
        data = resp.json()
        assert data["checks"]["redis"] == "ok"
        assert data["checks"]["postgres"] == "unavailable"
        # degraded because postgres is still down
        assert data["status"] == "degraded"
