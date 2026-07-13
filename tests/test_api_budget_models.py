"""Tests for GET /budget/models — per-model cost breakdown endpoint."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, patch

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient

from silkroute.api.app import create_app
from silkroute.api.deps import get_redis
from silkroute.config.settings import SilkRouteSettings
from silkroute.daemon.queue import TaskQueue


@pytest.fixture
def fake_redis_client() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def mock_db_pool() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def app(
    test_settings: SilkRouteSettings,
    fake_redis_client: fakeredis.aioredis.FakeRedis,
    mock_db_pool: AsyncMock,
) -> TestClient:
    application = create_app(settings=test_settings)
    queue = TaskQueue(fake_redis_client, maxsize=100)
    application.state.redis = fake_redis_client
    application.state.queue = queue
    application.state.db_pool = mock_db_pool

    application.dependency_overrides[get_redis] = lambda: fake_redis_client

    return TestClient(application, raise_server_exceptions=False)


AUTH = {"Authorization": "Bearer test-secret"}


class TestBudgetModelsRoute:
    def test_route_not_shadowed_by_project_id_route(self, app: TestClient) -> None:
        """/budget/models must not be captured by the /budget/{project_id} route.

        Regression guard for the route-ordering rule already established in
        this codebase: list/static routes must be declared before parameterized
        ones in the same router, or FastAPI matches the wrong one first.
        """
        with patch(
            "silkroute.db.repositories.model_cost_snapshots.get_snapshots",
            new=AsyncMock(return_value=[]),
        ):
            response = app.get(
                "/budget/models?project_id=test-proj", headers=AUTH
            )
        assert response.status_code == 200
        # If shadowed by /budget/{project_id}, the response would be a
        # ProjectBudgetResponse shape (has "monthly_spent_usd"), not our
        # list shape (has "snapshots").
        assert "snapshots" in response.json()

    def test_returns_empty_list_when_no_db_pool(self, app: TestClient) -> None:
        app.app.state.db_pool = None
        response = app.get("/budget/models?project_id=test-proj", headers=AUTH)
        assert response.status_code == 200
        assert response.json() == {"snapshots": [], "count": 0}

    def test_returns_snapshots_from_repository(self, app: TestClient) -> None:
        fake_row = {
            "project_id": "test-proj",
            "model_id": "ollama/qwen2.5:14b",
            "provider": "ollama",
            "snapshot_date": datetime.date(2026, 3, 1),
            "total_cost_usd": 0.0,
            "total_requests": 7,
            "total_tokens": 23029,
        }
        with patch(
            "silkroute.db.repositories.model_cost_snapshots.get_snapshots",
            new=AsyncMock(return_value=[fake_row]),
        ):
            response = app.get(
                "/budget/models?project_id=test-proj", headers=AUTH
            )
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        assert body["snapshots"][0]["model_id"] == "ollama/qwen2.5:14b"

    def test_fails_open_on_repository_error(self, app: TestClient) -> None:
        with patch(
            "silkroute.db.repositories.model_cost_snapshots.get_snapshots",
            new=AsyncMock(side_effect=RuntimeError("db down")),
        ):
            response = app.get(
                "/budget/models?project_id=test-proj", headers=AUTH
            )
        assert response.status_code == 200
        assert response.json() == {"snapshots": [], "count": 0}
