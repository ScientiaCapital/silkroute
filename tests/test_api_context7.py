"""Tests for /context7 API routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from silkroute.api.app import create_app
from silkroute.config.settings import SilkRouteSettings
from silkroute.mantis.skills.context7 import Context7Result, DocSnippet, LibraryInfo


@pytest.fixture
def app(test_settings: SilkRouteSettings) -> TestClient:
    """Create a test client with mocked state (no real Redis/DB)."""
    application = create_app(settings=test_settings)
    application.state.redis = None
    application.state.queue = None
    application.state.db_pool = None
    return TestClient(application, raise_server_exceptions=False)


def _make_mock_client(
    resolve_return: LibraryInfo | None = None,
    query_return: Context7Result | None = None,
    resolve_side_effect: Exception | None = None,
    query_side_effect: Exception | None = None,
) -> MagicMock:
    """Build a mock Context7Client with configurable behavior."""
    client = MagicMock()
    if resolve_side_effect is not None:
        client.resolve_library = AsyncMock(side_effect=resolve_side_effect)
    else:
        client.resolve_library = AsyncMock(return_value=resolve_return)

    if query_side_effect is not None:
        client.query = AsyncMock(side_effect=query_side_effect)
    else:
        if query_return is None:
            query_return = Context7Result(library=None, snippets=[], truncated=False)
        client.query = AsyncMock(return_value=query_return)

    return client


class TestResolveLibrary:
    """POST /context7/resolve."""

    def test_resolve_found_returns_200(self, app: TestClient) -> None:
        lib = LibraryInfo(id="fastapi/fastapi", name="FastAPI", version="0.115.0", trust_score=0.95)
        mock_client = _make_mock_client(resolve_return=lib)

        with patch("silkroute.api.routes.context7._get_client", return_value=mock_client):
            resp = app.post("/context7/resolve", json={"library_name": "fastapi"})

        assert resp.status_code == 200

    def test_resolve_found_returns_correct_fields(self, app: TestClient) -> None:
        lib = LibraryInfo(id="fastapi/fastapi", name="FastAPI", version="0.115.0", trust_score=0.95)
        mock_client = _make_mock_client(resolve_return=lib)

        with patch("silkroute.api.routes.context7._get_client", return_value=mock_client):
            resp = app.post("/context7/resolve", json={"library_name": "fastapi"})

        data = resp.json()
        assert data["found"] is True
        assert data["library_id"] == "fastapi/fastapi"
        assert data["library_name"] == "FastAPI"
        assert data["version"] == "0.115.0"
        assert data["trust_score"] == pytest.approx(0.95)

    def test_resolve_not_found_returns_found_false(self, app: TestClient) -> None:
        mock_client = _make_mock_client(resolve_return=None)

        with patch("silkroute.api.routes.context7._get_client", return_value=mock_client):
            resp = app.post("/context7/resolve", json={"library_name": "totally_unknown_lib_xyz"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is False

    def test_resolve_network_error_returns_found_false(self, app: TestClient) -> None:
        """On network error, route should fail-open and return found=False."""
        mock_client = _make_mock_client(resolve_side_effect=RuntimeError("network timeout"))

        with patch("silkroute.api.routes.context7._get_client", return_value=mock_client):
            resp = app.post("/context7/resolve", json={"library_name": "somelib"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is False

    def test_resolve_missing_library_name_returns_422(self, app: TestClient) -> None:
        resp = app.post("/context7/resolve", json={})
        assert resp.status_code == 422

    def test_resolve_empty_library_name_returns_422(self, app: TestClient) -> None:
        resp = app.post("/context7/resolve", json={"library_name": ""})
        assert resp.status_code == 422

    def test_resolve_with_optional_query(self, app: TestClient) -> None:
        lib = LibraryInfo(id="pydantic/pydantic", name="Pydantic", version="2.0", trust_score=0.9)
        mock_client = _make_mock_client(resolve_return=lib)

        with patch("silkroute.api.routes.context7._get_client", return_value=mock_client):
            resp = app.post(
                "/context7/resolve",
                json={"library_name": "pydantic", "query": "validation"},
            )

        assert resp.status_code == 200
        assert resp.json()["found"] is True
        # Verify the query was passed through
        mock_client.resolve_library.assert_awaited_once_with("pydantic", "validation")


class TestQueryDocs:
    """POST /context7/query."""

    def test_query_with_snippets_returns_200(self, app: TestClient) -> None:
        snippets = [
            DocSnippet(
                title="Introduction",
                content="FastAPI is fast",
                url="https://example.com/intro",
                relevance=0.9,
            ),
        ]
        lib = LibraryInfo(id="fastapi/fastapi", name="FastAPI", version="0.115.0", trust_score=0.95)
        result = Context7Result(library=lib, snippets=snippets, truncated=False)
        mock_client = _make_mock_client(query_return=result)

        with patch("silkroute.api.routes.context7._get_client", return_value=mock_client):
            resp = app.post(
                "/context7/query",
                json={"library_name": "fastapi", "query": "routing"},
            )

        assert resp.status_code == 200

    def test_query_returns_snippets(self, app: TestClient) -> None:
        snippets = [
            DocSnippet(title="Intro", content="First snippet", url="https://a.com", relevance=0.9),
            DocSnippet(title="Usage", content="Second snippet", url="https://b.com", relevance=0.7),
        ]
        lib = LibraryInfo(id="fastapi/fastapi", name="FastAPI", version="0.115.0", trust_score=0.95)
        result = Context7Result(library=lib, snippets=snippets, truncated=False)
        mock_client = _make_mock_client(query_return=result)

        with patch("silkroute.api.routes.context7._get_client", return_value=mock_client):
            resp = app.post(
                "/context7/query",
                json={"library_name": "fastapi", "query": "routing"},
            )

        data = resp.json()
        assert data["library_name"] == "fastapi"
        assert len(data["snippets"]) == 2
        assert data["snippets"][0]["title"] == "Intro"
        assert data["snippets"][1]["title"] == "Usage"
        assert data["truncated"] is False

    def test_query_with_no_results_returns_empty_snippets(self, app: TestClient) -> None:
        result = Context7Result(library=None, snippets=[], truncated=False)
        mock_client = _make_mock_client(query_return=result)

        with patch("silkroute.api.routes.context7._get_client", return_value=mock_client):
            resp = app.post(
                "/context7/query",
                json={"library_name": "unknownlib", "query": "something"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["snippets"] == []
        assert data["error"] == ""

    def test_query_truncated_flag(self, app: TestClient) -> None:
        snippets = [DocSnippet(title="T", content="x" * 1000, url="", relevance=0.5)]
        lib = LibraryInfo(id="x/x", name="X", version="1.0", trust_score=0.8)
        result = Context7Result(library=lib, snippets=snippets, truncated=True)
        mock_client = _make_mock_client(query_return=result)

        with patch("silkroute.api.routes.context7._get_client", return_value=mock_client):
            resp = app.post(
                "/context7/query",
                json={"library_name": "x", "query": "something"},
            )

        assert resp.json()["truncated"] is True

    def test_query_error_returns_error_field(self, app: TestClient) -> None:
        """On exception, route should fail-open with error field populated."""
        mock_client = _make_mock_client(query_side_effect=RuntimeError("API unavailable"))

        with patch("silkroute.api.routes.context7._get_client", return_value=mock_client):
            resp = app.post(
                "/context7/query",
                json={"library_name": "somelib", "query": "something"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] != ""
        assert "API unavailable" in data["error"]

    def test_query_missing_library_name_returns_422(self, app: TestClient) -> None:
        resp = app.post("/context7/query", json={"query": "something"})
        assert resp.status_code == 422

    def test_query_missing_query_returns_422(self, app: TestClient) -> None:
        resp = app.post("/context7/query", json={"library_name": "fastapi"})
        assert resp.status_code == 422

    def test_query_empty_query_returns_422(self, app: TestClient) -> None:
        resp = app.post("/context7/query", json={"library_name": "fastapi", "query": ""})
        assert resp.status_code == 422

    def test_query_snippet_has_expected_fields(self, app: TestClient) -> None:
        snippets = [
            DocSnippet(
                title="Guide",
                content="some content",
                url="https://docs.example.com",
                relevance=0.85,
            ),
        ]
        lib = LibraryInfo(id="pkg/pkg", name="pkg", version="1.0", trust_score=0.7)
        result = Context7Result(library=lib, snippets=snippets, truncated=False)
        mock_client = _make_mock_client(query_return=result)

        with patch("silkroute.api.routes.context7._get_client", return_value=mock_client):
            resp = app.post(
                "/context7/query",
                json={"library_name": "pkg", "query": "guide"},
            )

        snippet = resp.json()["snippets"][0]
        assert "title" in snippet
        assert "content" in snippet
        assert "url" in snippet
        assert "relevance" in snippet
