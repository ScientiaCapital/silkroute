"""Context7 REST API client for documentation lookup.

Fetches relevant documentation snippets for a library/query using the
Context7 public API. Fail-open: any network or API error returns an
empty result rather than raising.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

log = structlog.get_logger()

_CONTEXT7_BASE_URL = "https://context7.com"
_CHARS_PER_TOKEN = 4  # rough approximation


@dataclass
class LibraryInfo:
    """Resolved library metadata from Context7."""

    id: str
    name: str
    version: str
    trust_score: float


@dataclass
class DocSnippet:
    """A single documentation snippet returned by Context7."""

    title: str
    content: str
    url: str
    relevance: float


@dataclass
class Context7Result:
    """Combined result from a Context7 query."""

    library: LibraryInfo | None
    snippets: list[DocSnippet]
    truncated: bool = False


class Context7Client:
    """Async client for the Context7 documentation API.

    Args:
        base_url: Base URL for Context7 (default: https://context7.com).
        api_key: Optional API key for higher rate limits.
        timeout: HTTP request timeout in seconds.
        max_snippets: Maximum number of snippets to return.
        max_context_tokens: Token budget for returned snippets (4 chars/token).
        max_concurrent: Semaphore cap for concurrent requests.
        http_client: Injectable httpx.AsyncClient for testing.
    """

    def __init__(
        self,
        base_url: str = _CONTEXT7_BASE_URL,
        api_key: str = "",
        timeout: int = 10,
        max_snippets: int = 20,
        max_context_tokens: int = 8000,
        max_concurrent: int = 3,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._max_snippets = max_snippets
        self._max_context_tokens = max_context_tokens
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._http_client = http_client
        self._owns_client = http_client is None

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is not None:
            return self._http_client
        return httpx.AsyncClient(timeout=self._timeout)

    async def resolve_library(self, name: str, query: str = "") -> LibraryInfo | None:
        """Resolve a library name to a Context7 LibraryInfo.

        Returns None if not found or on any error (fail-open).
        """
        url = f"{self._base_url}/api/v2/libs/search"
        params: dict[str, Any] = {"libraryName": name}
        if query:
            params["query"] = query

        async with self._semaphore:
            try:
                client = await self._get_client()
                response = await client.get(url, params=params, headers=self._build_headers())
                response.raise_for_status()
                data = response.json()

                # API returns list of results; take first match
                results = data if isinstance(data, list) else data.get("results", [])
                if not results:
                    return None

                first = results[0]
                return LibraryInfo(
                    id=str(first.get("id", first.get("libraryId", ""))),
                    name=str(first.get("name", name)),
                    version=str(first.get("version", "unknown")),
                    trust_score=float(first.get("trustScore", first.get("trust_score", 0.0))),
                )
            except httpx.HTTPStatusError as e:
                log.warning(
                    "context7_resolve_http_error",
                    library=name,
                    status=e.response.status_code,
                )
                return None
            except httpx.RequestError as e:
                log.warning("context7_resolve_request_error", library=name, error=str(e))
                return None
            except Exception as e:
                log.warning("context7_resolve_error", library=name, error=str(e), exc_info=True)
                return None

    async def get_docs(self, library_id: str, query: str) -> list[DocSnippet]:
        """Fetch documentation snippets for a library_id + query.

        Clips results to max_snippets and max_context_tokens. Fail-open.
        """
        url = f"{self._base_url}/api/v2/context"
        params: dict[str, Any] = {
            "libraryId": library_id,
            "query": query,
            "type": "json",
        }

        async with self._semaphore:
            try:
                client = await self._get_client()
                response = await client.get(url, params=params, headers=self._build_headers())
                response.raise_for_status()
                data = response.json()

                raw_snippets = data if isinstance(data, list) else data.get("snippets", [])
                snippets: list[DocSnippet] = []
                tokens_used = 0
                max_chars = self._max_context_tokens * _CHARS_PER_TOKEN

                for raw in raw_snippets[: self._max_snippets]:
                    content = str(raw.get("content", raw.get("text", "")))
                    remaining_chars = max_chars - tokens_used
                    if remaining_chars <= 0:
                        break
                    if len(content) > remaining_chars:
                        content = content[:remaining_chars]

                    snippet = DocSnippet(
                        title=str(raw.get("title", "")),
                        content=content,
                        url=str(raw.get("url", "")),
                        relevance=float(raw.get("relevance", raw.get("score", 0.0))),
                    )
                    snippets.append(snippet)
                    tokens_used += len(content)

                return snippets
            except httpx.HTTPStatusError as e:
                log.warning(
                    "context7_get_docs_http_error",
                    library_id=library_id,
                    status=e.response.status_code,
                )
                return []
            except httpx.RequestError as e:
                log.warning(
                    "context7_get_docs_request_error",
                    library_id=library_id,
                    error=str(e),
                )
                return []
            except Exception as e:
                log.warning(
                    "context7_docs_error",
                    library_id=library_id,
                    error=str(e),
                    exc_info=True,
                )
                return []

    async def query(self, library_name: str, query: str) -> Context7Result:
        """Convenience method: resolve library then fetch docs.

        Combines resolve_library() + get_docs() into a single call.
        Always returns a Context7Result (fail-open on errors).
        """
        library = await self.resolve_library(library_name, query)
        if library is None:
            return Context7Result(library=None, snippets=[], truncated=False)

        snippets = await self.get_docs(library.id, query)

        # Determine if truncation occurred
        max_chars = self._max_context_tokens * _CHARS_PER_TOKEN
        total_chars = sum(len(s.content) for s in snippets)
        truncated = total_chars >= max_chars

        return Context7Result(library=library, snippets=snippets, truncated=truncated)
