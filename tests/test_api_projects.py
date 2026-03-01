"""Tests for /projects CRUD endpoints."""

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

SAMPLE_PROJECT = {
    "id": "test-proj",
    "name": "Test Project",
    "description": "A test",
    "github_repo": "org/repo",
    "budget_monthly_usd": 2.85,
    "budget_daily_usd": 0.10,
    "created_at": "2026-01-01T00:00:00+00:00",
    "updated_at": "2026-01-01T00:00:00+00:00",
}


class TestCreateProject:
    def test_create_returns_201(self, app: TestClient, mock_db_pool: AsyncMock) -> None:
        mock_db_pool.fetchrow.return_value = SAMPLE_PROJECT
        resp = app.post(
            "/projects",
            json={"id": "test-proj", "name": "Test Project", "description": "A test", "github_repo": "org/repo"},
            headers=AUTH,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "test-proj"
        assert data["name"] == "Test Project"

    def test_create_duplicate_returns_409(self, app: TestClient, mock_db_pool: AsyncMock) -> None:
        import asyncpg
        mock_db_pool.fetchrow.side_effect = asyncpg.UniqueViolationError("")
        resp = app.post(
            "/projects",
            json={"id": "dupe", "name": "Dupe"},
            headers=AUTH,
        )
        assert resp.status_code == 409

    def test_create_requires_auth(self, app: TestClient) -> None:
        resp = app.post("/projects", json={"id": "x", "name": "X"})
        assert resp.status_code == 401

    def test_create_invalid_id(self, app: TestClient) -> None:
        resp = app.post(
            "/projects",
            json={"id": "UPPER_CASE!", "name": "Bad ID"},
            headers=AUTH,
        )
        assert resp.status_code == 422

    def test_create_missing_name(self, app: TestClient) -> None:
        resp = app.post(
            "/projects",
            json={"id": "valid-id"},
            headers=AUTH,
        )
        assert resp.status_code == 422


class TestListProjects:
    def test_list_returns_projects(self, app: TestClient, mock_db_pool: AsyncMock) -> None:
        mock_db_pool.fetch.return_value = [SAMPLE_PROJECT]
        resp = app.get("/projects", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["projects"]) == 1

    def test_list_empty(self, app: TestClient, mock_db_pool: AsyncMock) -> None:
        mock_db_pool.fetch.return_value = []
        resp = app.get("/projects", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["projects"] == []

    def test_list_requires_auth(self, app: TestClient) -> None:
        resp = app.get("/projects")
        assert resp.status_code == 401

    def test_list_no_db_returns_empty(self, app: TestClient) -> None:
        app.app.state.db_pool = None
        resp = app.get("/projects", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


class TestGetProject:
    def test_get_returns_project(self, app: TestClient, mock_db_pool: AsyncMock) -> None:
        mock_db_pool.fetchrow.return_value = SAMPLE_PROJECT
        resp = app.get("/projects/test-proj", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["id"] == "test-proj"

    def test_get_not_found(self, app: TestClient, mock_db_pool: AsyncMock) -> None:
        mock_db_pool.fetchrow.return_value = None
        resp = app.get("/projects/nonexistent", headers=AUTH)
        assert resp.status_code == 404

    def test_get_requires_auth(self, app: TestClient) -> None:
        resp = app.get("/projects/test-proj")
        assert resp.status_code == 401


class TestUpdateProject:
    def test_patch_returns_updated(self, app: TestClient, mock_db_pool: AsyncMock) -> None:
        updated = {**SAMPLE_PROJECT, "name": "Updated Name"}
        mock_db_pool.fetchrow.return_value = updated
        resp = app.patch(
            "/projects/test-proj",
            json={"name": "Updated Name"},
            headers=AUTH,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    def test_patch_not_found(self, app: TestClient, mock_db_pool: AsyncMock) -> None:
        mock_db_pool.fetchrow.return_value = None
        resp = app.patch(
            "/projects/nonexistent",
            json={"name": "New"},
            headers=AUTH,
        )
        assert resp.status_code == 404

    def test_patch_requires_auth(self, app: TestClient) -> None:
        resp = app.patch("/projects/test-proj", json={"name": "X"})
        assert resp.status_code == 401


class TestDeleteProject:
    def test_delete_returns_success(self, app: TestClient, mock_db_pool: AsyncMock) -> None:
        mock_db_pool.execute.return_value = "DELETE 1"
        resp = app.delete("/projects/test-proj", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_delete_not_found(self, app: TestClient, mock_db_pool: AsyncMock) -> None:
        mock_db_pool.execute.return_value = "DELETE 0"
        resp = app.delete("/projects/nonexistent", headers=AUTH)
        assert resp.status_code == 404

    def test_delete_default_blocked(self, app: TestClient, mock_db_pool: AsyncMock) -> None:
        resp = app.delete("/projects/default", headers=AUTH)
        assert resp.status_code == 400
        assert "default" in resp.json()["detail"].lower()

    def test_delete_fk_violation(self, app: TestClient, mock_db_pool: AsyncMock) -> None:
        import asyncpg
        mock_db_pool.execute.side_effect = asyncpg.ForeignKeyViolationError("")
        resp = app.delete("/projects/has-costs", headers=AUTH)
        assert resp.status_code == 409

    def test_delete_requires_auth(self, app: TestClient) -> None:
        resp = app.delete("/projects/test-proj")
        assert resp.status_code == 401
