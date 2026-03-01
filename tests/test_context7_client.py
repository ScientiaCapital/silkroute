"""Tests for mantis/skills/context7.py — Context7Client."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from silkroute.mantis.skills.context7 import (
    Context7Client,
    Context7Result,
    DocSnippet,
    LibraryInfo,
)


def _make_response(json_data: object, status_code: int = 200) -> MagicMock:
    """Create a mock httpx.Response."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data
    mock_resp.raise_for_status = MagicMock()
    if status_code >= 400:
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message="error",
            request=MagicMock(),
            response=mock_resp,
        )
    return mock_resp


def _make_client(get_response: object | None = None) -> tuple[Context7Client, MagicMock]:
    """Create a Context7Client with a mocked httpx.AsyncClient."""
    mock_http = MagicMock(spec=httpx.AsyncClient)
    mock_http.get = AsyncMock(return_value=get_response)
    client = Context7Client(http_client=mock_http)
    return client, mock_http


_LIBRARY_SEARCH_RESPONSE = [
    {
        "id": "lib/fastapi",
        "name": "FastAPI",
        "version": "0.115.0",
        "trustScore": 0.95,
    }
]

_DOCS_RESPONSE = {
    "snippets": [
        {
            "title": "Getting Started",
            "content": "FastAPI is a modern web framework for Python.",
            "url": "https://fastapi.tiangolo.com",
            "relevance": 0.98,
        },
        {
            "title": "Routing",
            "content": "Use @app.get() decorator to define routes.",
            "url": "https://fastapi.tiangolo.com/routing",
            "relevance": 0.85,
        },
    ]
}


class TestResolveLibrary:
    """Context7Client.resolve_library()."""

    async def test_resolve_library_success(self) -> None:
        client, mock_http = _make_client(
            get_response=_make_response(_LIBRARY_SEARCH_RESPONSE)
        )
        result = await client.resolve_library("fastapi")
        assert result is not None
        assert result.id == "lib/fastapi"
        assert result.name == "FastAPI"
        assert result.version == "0.115.0"
        assert result.trust_score == 0.95

    async def test_resolve_library_not_found(self) -> None:
        client, mock_http = _make_client(get_response=_make_response([]))
        result = await client.resolve_library("nonexistent_lib_xyz")
        assert result is None

    async def test_resolve_library_network_error_fail_open(self) -> None:
        mock_http = MagicMock(spec=httpx.AsyncClient)
        mock_http.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        client = Context7Client(http_client=mock_http)

        result = await client.resolve_library("fastapi")
        assert result is None  # fail-open

    async def test_resolve_library_http_error_fail_open(self) -> None:
        client, mock_http = _make_client(get_response=_make_response({}, status_code=500))
        result = await client.resolve_library("fastapi")
        assert result is None  # fail-open

    async def test_resolve_library_with_api_key_sends_auth_header(self) -> None:
        mock_http = MagicMock(spec=httpx.AsyncClient)
        mock_http.get = AsyncMock(return_value=_make_response(_LIBRARY_SEARCH_RESPONSE))
        client = Context7Client(api_key="my-secret-key", http_client=mock_http)

        await client.resolve_library("fastapi")

        call_kwargs = mock_http.get.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer my-secret-key"


class TestGetDocs:
    """Context7Client.get_docs()."""

    async def test_get_docs_success(self) -> None:
        client, mock_http = _make_client(get_response=_make_response(_DOCS_RESPONSE))
        snippets = await client.get_docs("lib/fastapi", "routing")
        assert len(snippets) == 2
        assert snippets[0].title == "Getting Started"
        assert snippets[0].content == "FastAPI is a modern web framework for Python."
        assert snippets[0].url == "https://fastapi.tiangolo.com"
        assert snippets[0].relevance == 0.98

    async def test_get_docs_network_error_fail_open(self) -> None:
        mock_http = MagicMock(spec=httpx.AsyncClient)
        mock_http.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        client = Context7Client(http_client=mock_http)
        snippets = await client.get_docs("lib/fastapi", "routing")
        assert snippets == []  # fail-open

    async def test_get_docs_token_truncation(self) -> None:
        # max_context_tokens=5 => max_chars=20
        long_content = "A" * 100
        response_data = {
            "snippets": [
                {"title": "Long", "content": long_content, "url": "", "relevance": 1.0},
            ]
        }
        mock_http = MagicMock(spec=httpx.AsyncClient)
        mock_http.get = AsyncMock(return_value=_make_response(response_data))
        client = Context7Client(max_context_tokens=5, http_client=mock_http)

        snippets = await client.get_docs("lib/test", "query")
        assert len(snippets) == 1
        # 5 tokens * 4 chars/token = 20 chars max
        assert len(snippets[0].content) == 20

    async def test_get_docs_max_snippets_limit(self) -> None:
        many_snippets = [
            {"title": f"S{i}", "content": f"Content {i}", "url": "", "relevance": 0.5}
            for i in range(30)
        ]
        response_data = {"snippets": many_snippets}
        mock_http = MagicMock(spec=httpx.AsyncClient)
        mock_http.get = AsyncMock(return_value=_make_response(response_data))
        client = Context7Client(max_snippets=5, http_client=mock_http)

        snippets = await client.get_docs("lib/test", "query")
        assert len(snippets) == 5


class TestQueryConvenience:
    """Context7Client.query() — resolve + fetch combined."""

    async def test_query_success(self) -> None:
        mock_http = MagicMock(spec=httpx.AsyncClient)
        # First call: search, second call: docs
        mock_http.get = AsyncMock(side_effect=[
            _make_response(_LIBRARY_SEARCH_RESPONSE),
            _make_response(_DOCS_RESPONSE),
        ])
        client = Context7Client(http_client=mock_http)

        result = await client.query("fastapi", "routing")
        assert isinstance(result, Context7Result)
        assert result.library is not None
        assert result.library.name == "FastAPI"
        assert len(result.snippets) == 2

    async def test_query_library_not_found(self) -> None:
        mock_http = MagicMock(spec=httpx.AsyncClient)
        mock_http.get = AsyncMock(return_value=_make_response([]))
        client = Context7Client(http_client=mock_http)

        result = await client.query("phantom_lib", "anything")
        assert result.library is None
        assert result.snippets == []

    async def test_query_truncated_flag(self) -> None:
        # With very small token budget, truncated should be True
        long_content = "X" * 1000
        library_resp = _make_response(_LIBRARY_SEARCH_RESPONSE)
        docs_resp = _make_response({
            "snippets": [
                {"title": "Big", "content": long_content, "url": "", "relevance": 1.0},
            ]
        })

        mock_http = MagicMock(spec=httpx.AsyncClient)
        mock_http.get = AsyncMock(side_effect=[library_resp, docs_resp])
        # max_context_tokens=10 => max_chars=40
        client = Context7Client(max_context_tokens=10, http_client=mock_http)

        result = await client.query("fastapi", "query")
        assert result.truncated is True


class TestSemaphoreRateLimiting:
    """Context7Client semaphore limits concurrency."""

    async def test_semaphore_limits_concurrent_requests(self) -> None:
        active_count = 0
        max_active = 0
        barrier = asyncio.Event()

        async def slow_get(*args: object, **kwargs: object) -> MagicMock:
            nonlocal active_count, max_active
            active_count += 1
            max_active = max(max_active, active_count)
            await asyncio.sleep(0)  # yield
            active_count -= 1
            return _make_response(_LIBRARY_SEARCH_RESPONSE)

        mock_http = MagicMock(spec=httpx.AsyncClient)
        mock_http.get = slow_get

        client = Context7Client(max_concurrent=2, http_client=mock_http)

        # Launch 5 concurrent resolve calls
        tasks = [client.resolve_library(f"lib{i}") for i in range(5)]
        await asyncio.gather(*tasks)

        # Due to the semaphore, max active should not exceed 2
        assert max_active <= 2
