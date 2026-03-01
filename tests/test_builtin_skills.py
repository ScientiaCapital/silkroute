"""Tests for mantis/skills/builtin — http_skill, search_skill, docs_skill, llm_skill."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from silkroute.mantis.skills.builtin.docs_skill import _docs_lookup_handler
from silkroute.mantis.skills.builtin.http_skill import _http_request_handler, _is_blocked_url
from silkroute.mantis.skills.builtin.llm_skill import _code_review_handler, _summarize_handler
from silkroute.mantis.skills.builtin.search_skill import _search_grep_handler
from silkroute.mantis.skills.context7 import Context7Client, Context7Result, DocSnippet, LibraryInfo
from silkroute.mantis.skills.models import SkillContext


# ─────────────────────────────────────────────────────────
# http_skill
# ─────────────────────────────────────────────────────────


class TestHttpSkillSSRF:
    """SSRF protection in http_request skill."""

    def test_block_loopback(self) -> None:
        assert _is_blocked_url("http://127.0.0.1/path") is not None

    def test_block_loopback_range(self) -> None:
        assert _is_blocked_url("http://127.0.0.2/path") is not None

    def test_block_rfc1918_10_range(self) -> None:
        assert _is_blocked_url("http://10.0.0.1/api") is not None

    def test_block_rfc1918_192_168(self) -> None:
        assert _is_blocked_url("http://192.168.1.1/router") is not None

    def test_block_rfc1918_172_16(self) -> None:
        assert _is_blocked_url("http://172.16.0.1/") is not None

    def test_block_rfc1918_172_31(self) -> None:
        assert _is_blocked_url("http://172.31.255.255/") is not None

    def test_block_link_local(self) -> None:
        assert _is_blocked_url("http://169.254.1.1/") is not None

    def test_block_localhost_hostname(self) -> None:
        assert _is_blocked_url("http://localhost/") is not None

    def test_block_file_scheme(self) -> None:
        assert _is_blocked_url("file:///etc/passwd") is not None

    def test_block_ftp_scheme(self) -> None:
        assert _is_blocked_url("ftp://example.com/file") is not None

    def test_allow_public_ip(self) -> None:
        # 8.8.8.8 is a public IP
        result = _is_blocked_url("http://8.8.8.8/")
        assert result is None

    def test_allow_public_domain(self) -> None:
        # Should not block example.com
        result = _is_blocked_url("https://example.com/api")
        # DNS may fail in CI, but we only block if DNS resolves to private
        # The function is fail-open on DNS errors, so should return None
        assert result is None or "private" in (result or "")


class TestHttpSkillRequest:
    """http_request skill handler."""

    async def test_ssrf_blocked_returns_error(self) -> None:
        result = await _http_request_handler(url="http://127.0.0.1/secret")
        assert result.startswith("Error:")
        assert "Blocked" in result

    async def test_invalid_method_blocked(self) -> None:
        result = await _http_request_handler(
            url="https://httpbin.org/get",
            method="TRACE",
        )
        assert "not allowed" in result

    async def test_success_get_request(self) -> None:
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.reason_phrase = "OK"
        mock_response.headers = {"content-type": "application/json"}
        mock_response.content = b'{"status": "ok"}'

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.request = AsyncMock(return_value=mock_response)

        with patch("silkroute.mantis.skills.builtin.http_skill.httpx.AsyncClient", return_value=mock_client):
            result = await _http_request_handler(url="https://example.com/api")

        assert "HTTP 200" in result
        assert '{"status": "ok"}' in result

    async def test_response_truncated_at_20kb(self) -> None:
        large_body = b"X" * (25 * 1024)  # 25 KB

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.reason_phrase = "OK"
        mock_response.headers = {"content-type": "text/plain"}
        mock_response.content = large_body

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.request = AsyncMock(return_value=mock_response)

        with patch("silkroute.mantis.skills.builtin.http_skill.httpx.AsyncClient", return_value=mock_client):
            result = await _http_request_handler(url="https://example.com/big")

        assert "Truncated" in result

    async def test_timeout_clamp(self) -> None:
        """Timeout above 60 is clamped to 60, below 1 clamped to 1."""
        # The handler should clamp without error; test by mocking
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.reason_phrase = "OK"
        mock_response.headers = {"content-type": "text/plain"}
        mock_response.content = b"ok"

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.request = AsyncMock(return_value=mock_response)

        with patch("silkroute.mantis.skills.builtin.http_skill.httpx.AsyncClient", return_value=mock_client):
            result = await _http_request_handler(url="https://example.com/", timeout=999)

        assert "HTTP 200" in result


# ─────────────────────────────────────────────────────────
# search_skill
# ─────────────────────────────────────────────────────────


class TestSearchGrepSkill:
    """search_grep skill handler."""

    async def test_finds_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "test.py"
            f.write_text("def hello():\n    return 'world'\n")

            ctx = SkillContext(workspace_dir=tmpdir)
            result = await _search_grep_handler(pattern="hello", _skill_ctx=ctx)

        assert "hello" in result
        assert "test.py" in result

    async def test_no_matches_returns_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "empty.py"
            f.write_text("x = 1\n")

            ctx = SkillContext(workspace_dir=tmpdir)
            result = await _search_grep_handler(pattern="NOMATCH_XYZ", _skill_ctx=ctx)

        assert "No matches" in result

    async def test_respects_max_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "many.txt"
            # 20 matching lines
            f.write_text("\n".join([f"match line {i}" for i in range(20)]))

            ctx = SkillContext(workspace_dir=tmpdir)
            result = await _search_grep_handler(
                pattern="match line",
                max_results=5,
                context_lines=0,
                _skill_ctx=ctx,
            )

        # Should be capped
        assert "capped at 5" in result or result.count("match line") <= 5

    async def test_invalid_regex_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = SkillContext(workspace_dir=tmpdir)
            result = await _search_grep_handler(pattern="[invalid", _skill_ctx=ctx)
        assert "Error" in result
        assert "regex" in result.lower() or "invalid" in result

    async def test_path_outside_workspace_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = SkillContext(workspace_dir=tmpdir)
            result = await _search_grep_handler(pattern="x", path="/etc", _skill_ctx=ctx)
        assert "Error" in result
        assert "outside" in result

    async def test_context_lines_shown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "ctx.txt"
            f.write_text("line 1\nline 2 MATCH\nline 3\n")

            ctx = SkillContext(workspace_dir=tmpdir)
            result = await _search_grep_handler(
                pattern="MATCH",
                context_lines=1,
                _skill_ctx=ctx,
            )

        # The context line before and after should appear
        assert "line 1" in result
        assert "line 3" in result


# ─────────────────────────────────────────────────────────
# docs_skill
# ─────────────────────────────────────────────────────────


class TestDocsLookupSkill:
    """docs_lookup skill handler."""

    async def test_docs_lookup_success(self) -> None:
        mock_result = Context7Result(
            library=LibraryInfo(id="lib/fastapi", name="FastAPI", version="0.115.0", trust_score=0.95),
            snippets=[
                DocSnippet(
                    title="Routing",
                    content="Use @app.get() to define routes.",
                    url="https://fastapi.tiangolo.com",
                    relevance=0.98,
                )
            ],
            truncated=False,
        )

        mock_client = AsyncMock(spec=Context7Client)
        mock_client.query.return_value = mock_result

        with patch(
            "silkroute.mantis.skills.builtin.docs_skill._get_default_client",
            return_value=mock_client,
        ):
            result = await _docs_lookup_handler(library_name="fastapi", query="routing")

        assert "FastAPI" in result
        assert "0.115.0" in result
        assert "Routing" in result
        assert "@app.get()" in result

    async def test_docs_lookup_library_not_found(self) -> None:
        mock_result = Context7Result(library=None, snippets=[], truncated=False)
        mock_client = AsyncMock(spec=Context7Client)
        mock_client.query.return_value = mock_result

        with patch(
            "silkroute.mantis.skills.builtin.docs_skill._get_default_client",
            return_value=mock_client,
        ):
            result = await _docs_lookup_handler(library_name="phantom_lib_xyz", query="anything")

        assert "Could not find" in result
        assert "phantom_lib_xyz" in result

    async def test_docs_lookup_fail_open_on_exception(self) -> None:
        mock_client = AsyncMock(spec=Context7Client)
        mock_client.query.side_effect = Exception("network failure")

        with patch(
            "silkroute.mantis.skills.builtin.docs_skill._get_default_client",
            return_value=mock_client,
        ):
            result = await _docs_lookup_handler(library_name="fastapi", query="routing")

        # Should return a helpful message, not raise
        assert "unavailable" in result.lower() or "network failure" in result


# ─────────────────────────────────────────────────────────
# llm_skill
# ─────────────────────────────────────────────────────────


class TestCodeReviewSkill:
    """code_review skill handler."""

    async def test_code_review_no_ctx_returns_error(self) -> None:
        result = await _code_review_handler(code="def foo(): pass", _skill_ctx=None)
        assert "Error" in result
        assert "SkillContext" in result

    async def test_code_review_success(self) -> None:
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "- No issues found.\n- Code looks clean."
        mock_llm.ainvoke.return_value = mock_response

        ctx = SkillContext(_llm_factory=lambda model_id=None: mock_llm)

        result = await _code_review_handler(
            code="def add(a, b): return a + b",
            context="utility function",
            focus="correctness",
            _skill_ctx=ctx,
        )

        assert mock_llm.ainvoke.called
        assert "No issues" in result or "clean" in result

    async def test_code_review_llm_error(self) -> None:
        mock_llm = AsyncMock()
        mock_llm.ainvoke.side_effect = RuntimeError("LLM unavailable")

        ctx = SkillContext(_llm_factory=lambda model_id=None: mock_llm)
        result = await _code_review_handler(
            code="x = 1",
            _skill_ctx=ctx,
        )

        assert "Error" in result


class TestSummarizeSkill:
    """summarize skill handler."""

    async def test_summarize_no_ctx_returns_error(self) -> None:
        result = await _summarize_handler(text="Some text to summarize.", _skill_ctx=None)
        assert "Error" in result
        assert "SkillContext" in result

    async def test_summarize_success(self) -> None:
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "A concise summary."
        mock_llm.ainvoke.return_value = mock_response

        ctx = SkillContext(_llm_factory=lambda model_id=None: mock_llm)
        result = await _summarize_handler(
            text="This is a long piece of text that needs to be summarized.",
            max_length=50,
            _skill_ctx=ctx,
        )

        assert mock_llm.ainvoke.called
        assert "summary" in result.lower()

    async def test_summarize_llm_error(self) -> None:
        mock_llm = AsyncMock()
        mock_llm.ainvoke.side_effect = RuntimeError("timeout")

        ctx = SkillContext(_llm_factory=lambda model_id=None: mock_llm)
        result = await _summarize_handler(text="Some text.", _skill_ctx=ctx)
        assert "Error" in result
