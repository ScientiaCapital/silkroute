"""Tests for api/routes/supervisor.py — supervisor API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from silkroute.api.app import create_app
from silkroute.config.settings import ApiConfig, ProviderConfig, SilkRouteSettings
from silkroute.mantis.supervisor.models import SessionStatus


@pytest.fixture
def test_settings():
    return SilkRouteSettings(
        providers=ProviderConfig(ollama_enabled=True),
        api=ApiConfig(api_key="test-secret"),
    )


@pytest.fixture
def client(test_settings):
    app = create_app(test_settings)
    app.dependency_overrides.clear()

    # Override DB pool and lifespan deps
    from silkroute.api import deps
    app.dependency_overrides[deps.get_settings] = lambda: test_settings
    app.dependency_overrides[deps.get_db_pool] = lambda: None

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


AUTH_HEADERS = {"Authorization": "Bearer test-secret"}


class TestCreateSession:
    """POST /supervisor/sessions"""

    @patch("silkroute.api.routes.supervisor.SupervisorRuntime")
    def test_create_session_success(self, MockRT, client):
        mock_rt = MockRT.return_value
        mock_rt.create_session = AsyncMock()
        mock_rt._run_session = AsyncMock()

        from silkroute.mantis.runtime.interface import AgentResult
        from silkroute.mantis.supervisor.models import SupervisorSession, SupervisorPlan, SupervisorStep

        session = SupervisorSession(
            id="sess-test",
            plan=SupervisorPlan(steps=[SupervisorStep(id="a", name="step1")]),
            status=SessionStatus.COMPLETED,
        )
        mock_rt.create_session.return_value = session
        mock_rt._run_session.return_value = AgentResult(
            status="completed", cost_usd=0.05,
        )

        resp = client.post(
            "/supervisor/sessions",
            json={
                "description": "review and fix",
                "steps": [
                    {"name": "review", "description": "review code"},
                    {"name": "fix", "description": "fix bugs"},
                ],
            },
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"

    def test_create_session_no_auth(self, client):
        resp = client.post(
            "/supervisor/sessions",
            json={
                "description": "test",
                "steps": [{"name": "step1"}],
            },
        )
        assert resp.status_code == 401

    def test_create_session_validation_error(self, client):
        resp = client.post(
            "/supervisor/sessions",
            json={
                "description": "test",
                "steps": [],  # min_length=1 violated
            },
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 422


class TestListSessions:
    """GET /supervisor/sessions"""

    def test_list_sessions_no_db(self, client):
        resp = client.get(
            "/supervisor/sessions",
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 503

    @patch("silkroute.db.repositories.supervisor.list_supervisor_sessions")
    def test_list_sessions_empty(self, mock_list, client):
        # Override db_pool to non-None so the endpoint proceeds
        from silkroute.api import deps
        from unittest.mock import AsyncMock
        mock_pool = AsyncMock()
        client.app.dependency_overrides[deps.get_db_pool] = lambda: mock_pool
        mock_list.return_value = []

        resp = client.get(
            "/supervisor/sessions",
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json() == []

        # Restore
        client.app.dependency_overrides[deps.get_db_pool] = lambda: None

    def test_list_sessions_no_auth(self, client):
        resp = client.get("/supervisor/sessions")
        assert resp.status_code == 401


class TestGetSession:
    """GET /supervisor/sessions/{id}"""

    def test_get_session_no_db(self, client):
        resp = client.get(
            "/supervisor/sessions/nonexistent",
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 503  # DB unavailable


class TestResumeSession:
    """POST /supervisor/sessions/{id}/resume"""

    @patch("silkroute.api.routes.supervisor.SupervisorRuntime")
    def test_resume_not_found(self, MockRT, client):
        mock_rt = MockRT.return_value

        from silkroute.mantis.runtime.interface import AgentResult

        mock_rt.resume_session = AsyncMock(return_value=AgentResult(
            status="failed",
            error="Session nonexist not found",
        ))

        resp = client.post(
            "/supervisor/sessions/nonexist/resume",
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 404


class TestCancelSession:
    """DELETE /supervisor/sessions/{id}"""

    @patch("silkroute.api.routes.supervisor.SupervisorRuntime")
    def test_cancel_not_found(self, MockRT, client):
        mock_rt = MockRT.return_value
        mock_rt.cancel_session = AsyncMock(return_value=False)

        resp = client.delete(
            "/supervisor/sessions/nonexist",
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 404

    @patch("silkroute.api.routes.supervisor.SupervisorRuntime")
    def test_cancel_success(self, MockRT, client):
        mock_rt = MockRT.return_value
        mock_rt.cancel_session = AsyncMock(return_value=True)

        resp = client.delete(
            "/supervisor/sessions/sess-1",
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"
