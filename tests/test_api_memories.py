"""Tests for /memories API routes."""

from __future__ import annotations

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


class TestListMemoriesRoute:
    def test_returns_available_false_when_no_db_pool(self, app: TestClient) -> None:
        app.app.state.db_pool = None
        response = app.get("/memories", headers=AUTH)
        assert response.status_code == 200
        assert response.json() == {"items": [], "count": 0, "available": False}

    def test_returns_items_from_repository(self, app: TestClient) -> None:
        fake_row = {
            "id": 1,
            "project_id": "proj-1",
            "kind": "fact",
            "content": "x",
            "importance": 0.5,
            "recall_count": 2,
            "created_at": "2026-07-17T00:00:00",
        }
        with patch(
            "silkroute.db.repositories.memories.list_memories",
            new=AsyncMock(return_value=[fake_row]),
        ):
            response = app.get("/memories", headers=AUTH)
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        assert body["items"][0]["content"] == "x"
        assert body["available"] is True

    def test_fails_open_on_repository_error(self, app: TestClient) -> None:
        with patch(
            "silkroute.db.repositories.memories.list_memories",
            new=AsyncMock(side_effect=RuntimeError("db down")),
        ):
            response = app.get("/memories", headers=AUTH)
        assert response.status_code == 200
        assert response.json() == {"items": [], "count": 0, "available": False}

    def test_requires_auth(self, app: TestClient) -> None:
        response = app.get("/memories")
        assert response.status_code == 401


class TestForgetMemoryRoute:
    def test_returns_503_when_no_db_pool(self, app: TestClient) -> None:
        app.app.state.db_pool = None
        response = app.delete("/memories/1", headers=AUTH)
        assert response.status_code == 503

    def test_returns_404_when_missing(self, app: TestClient) -> None:
        with patch(
            "silkroute.db.repositories.memories.delete_memory",
            new=AsyncMock(return_value=False),
        ):
            response = app.delete("/memories/999", headers=AUTH)
        assert response.status_code == 404

    def test_returns_200_when_deleted(self, app: TestClient) -> None:
        with patch(
            "silkroute.db.repositories.memories.delete_memory",
            new=AsyncMock(return_value=True),
        ):
            response = app.delete("/memories/1", headers=AUTH)
        assert response.status_code == 200
        assert response.json() == {"deleted": True}
