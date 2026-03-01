"""Tests for /skills API routes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from silkroute.api.app import create_app
from silkroute.config.settings import SilkRouteSettings
from silkroute.mantis.skills import SkillRegistry
from silkroute.mantis.skills.builtin import register_builtin_skills
from silkroute.mantis.skills.models import SkillCategory


@pytest.fixture
def app(test_settings: SilkRouteSettings) -> TestClient:
    """Create a test client with mocked state (no real Redis/DB)."""
    application = create_app(settings=test_settings)
    application.state.redis = None
    application.state.queue = None
    application.state.db_pool = None
    registry = SkillRegistry()
    register_builtin_skills(registry)
    application.state.skill_registry = registry
    return TestClient(application, raise_server_exceptions=False)


class TestListSkills:
    """GET /skills — list all available skills."""

    def test_returns_200(self, app: TestClient) -> None:
        resp = app.get("/skills")
        assert resp.status_code == 200

    def test_returns_list(self, app: TestClient) -> None:
        resp = app.get("/skills")
        data = resp.json()
        assert isinstance(data, list)

    def test_non_empty_list(self, app: TestClient) -> None:
        """Built-in skills should be registered so list is never empty."""
        resp = app.get("/skills")
        data = resp.json()
        assert len(data) > 0

    def test_skill_has_expected_fields(self, app: TestClient) -> None:
        resp = app.get("/skills")
        skill = resp.json()[0]
        assert "name" in skill
        assert "description" in skill
        assert "category" in skill
        assert "parameters" in skill
        assert "is_llm_native" in skill
        assert "max_budget_usd" in skill
        assert "version" in skill
        assert "required_tools" in skill

    def test_all_skills_have_valid_category(self, app: TestClient) -> None:
        """Every skill's category must be a valid SkillCategory value."""
        valid_categories = {c.value for c in SkillCategory}
        resp = app.get("/skills")
        for skill in resp.json():
            assert skill["category"] in valid_categories, (
                f"Skill '{skill['name']}' has invalid category '{skill['category']}'"
            )

    def test_filter_by_valid_category(self, app: TestClient) -> None:
        """?category=web returns only web skills."""
        resp = app.get("/skills?category=web")
        assert resp.status_code == 200
        data = resp.json()
        for skill in data:
            assert skill["category"] == "web"

    def test_filter_by_search_category(self, app: TestClient) -> None:
        """?category=search returns only search skills."""
        resp = app.get("/skills?category=search")
        assert resp.status_code == 200
        data = resp.json()
        for skill in data:
            assert skill["category"] == "search"

    def test_invalid_category_returns_422(self, app: TestClient) -> None:
        """?category=bogus should return 422 validation error."""
        resp = app.get("/skills?category=bogus_invalid_category")
        assert resp.status_code == 422

    def test_skill_name_is_string(self, app: TestClient) -> None:
        resp = app.get("/skills")
        for skill in resp.json():
            assert isinstance(skill["name"], str)
            assert len(skill["name"]) > 0

    def test_skill_budget_is_positive(self, app: TestClient) -> None:
        resp = app.get("/skills")
        for skill in resp.json():
            assert skill["max_budget_usd"] > 0


class TestGetSkill:
    """GET /skills/{skill_id} — get a single skill."""

    def test_known_skill_returns_200(self, app: TestClient) -> None:
        resp = app.get("/skills/http_request")
        assert resp.status_code == 200

    def test_known_skill_returns_correct_name(self, app: TestClient) -> None:
        resp = app.get("/skills/http_request")
        data = resp.json()
        assert data["name"] == "http_request"

    def test_known_skill_has_valid_category(self, app: TestClient) -> None:
        resp = app.get("/skills/http_request")
        data = resp.json()
        valid_categories = {c.value for c in SkillCategory}
        assert data["category"] in valid_categories

    def test_search_skill_exists(self, app: TestClient) -> None:
        resp = app.get("/skills/search_grep")
        assert resp.status_code == 200
        assert resp.json()["category"] == "search"

    def test_unknown_skill_returns_404(self, app: TestClient) -> None:
        resp = app.get("/skills/no_such_skill_exists")
        assert resp.status_code == 404

    def test_404_error_message_contains_skill_name(self, app: TestClient) -> None:
        resp = app.get("/skills/nonexistent_skill")
        data = resp.json()
        assert "nonexistent_skill" in data.get("detail", "")
