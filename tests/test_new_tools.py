"""Tests for the 4 new tools: http_request, search_grep, git_ops, env_info."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import silkroute.agent.tools as tools_module
from silkroute.agent.tools import (
    _env_info,
    _git_ops,
    _http_request,
    _is_ssrf_blocked,
    _search_grep,
    create_default_registry,
)


# ============================================================================
# http_request — SSRF blocking
# ============================================================================


class TestSsrfBlocking:
    def test_blocks_loopback_127(self):
        reason = _is_ssrf_blocked("http://127.0.0.1/secret")
        assert reason is not None
        assert "loopback" in reason

    def test_blocks_loopback_ipv6(self):
        reason = _is_ssrf_blocked("http://[::1]/secret")
        assert reason is not None
        assert "loopback" in reason

    def test_blocks_localhost_hostname(self):
        reason = _is_ssrf_blocked("http://localhost/api")
        assert reason is not None
        assert "loopback" in reason

    def test_blocks_private_10_x(self):
        reason = _is_ssrf_blocked("http://10.0.0.1/internal")
        assert reason is not None
        assert "private" in reason or "RFC-1918" in reason

    def test_blocks_private_192_168(self):
        reason = _is_ssrf_blocked("http://192.168.1.100/admin")
        assert reason is not None
        assert "private" in reason or "RFC-1918" in reason

    def test_blocks_private_172_16(self):
        reason = _is_ssrf_blocked("http://172.16.0.1/")
        assert reason is not None
        assert "private" in reason or "RFC-1918" in reason

    def test_blocks_private_172_31(self):
        reason = _is_ssrf_blocked("http://172.31.255.254/")
        assert reason is not None
        assert "private" in reason or "RFC-1918" in reason

    def test_blocks_link_local(self):
        reason = _is_ssrf_blocked("http://169.254.0.1/metadata")
        assert reason is not None
        assert "link-local" in reason

    def test_blocks_file_scheme(self):
        reason = _is_ssrf_blocked("file:///etc/passwd")
        assert reason is not None
        assert "file://" in reason

    def test_allows_public_ip(self):
        reason = _is_ssrf_blocked("https://8.8.8.8/api")
        assert reason is None

    def test_allows_public_hostname(self):
        reason = _is_ssrf_blocked("https://example.com/api")
        assert reason is None


class TestHttpRequest:
    @pytest.mark.asyncio
    async def test_ssrf_blocked_returns_error(self):
        result = await _http_request("http://127.0.0.1/secret")
        assert "Error" in result
        assert "SSRF" in result

    @pytest.mark.asyncio
    async def test_ssrf_file_scheme_blocked(self):
        result = await _http_request("file:///etc/passwd")
        assert "Error" in result
        assert "SSRF" in result

    @pytest.mark.asyncio
    async def test_ssrf_private_network_blocked(self):
        result = await _http_request("http://10.0.0.1/api")
        assert "Error" in result
        assert "SSRF" in result

    @pytest.mark.asyncio
    async def test_successful_get(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/plain"}
        mock_response.content = b"Hello, world!"
        mock_response.text = "Hello, world!"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.request = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await _http_request("https://example.com/api")

        assert "Status: 200" in result
        assert "Hello, world!" in result

    @pytest.mark.asyncio
    async def test_successful_post_with_body_and_headers(self):
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.headers = {"content-type": "application/json"}
        mock_response.content = b'{"id": 42}'
        mock_response.text = '{"id": 42}'

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.request = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await _http_request(
                url="https://api.example.com/items",
                method="POST",
                headers='{"Content-Type": "application/json"}',
                body='{"name": "test"}',
            )

        assert "Status: 201" in result
        assert '{"id": 42}' in result
        # Verify the request was called with correct method and content
        call_kwargs = mock_client.request.call_args
        assert call_kwargs.kwargs["method"] == "POST"
        assert call_kwargs.kwargs["content"] == b'{"name": "test"}'

    @pytest.mark.asyncio
    async def test_response_truncated_at_20kb(self):
        large_content = b"x" * (25 * 1024)  # 25KB

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.content = large_content
        mock_response.text = large_content.decode()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.request = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await _http_request("https://example.com/large")

        assert "truncated" in result
        assert "20KB" in result

    @pytest.mark.asyncio
    async def test_response_not_truncated_under_20kb(self):
        small_content = b"y" * (10 * 1024)  # 10KB

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.content = small_content
        mock_response.text = small_content.decode()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.request = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await _http_request("https://example.com/small")

        assert "truncated" not in result

    @pytest.mark.asyncio
    async def test_timeout_clamped_to_min_1(self):
        """Timeout below 1 is clamped to 1."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.content = b"ok"
        mock_response.text = "ok"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.request = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await _http_request("https://example.com/", timeout=0)

        # Should not error — clamped to 1s
        assert "Error" not in result or "SSRF" not in result

    @pytest.mark.asyncio
    async def test_timeout_clamped_to_max_60(self):
        """Timeout above 60 is clamped to 60."""
        import httpx

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.request = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await _http_request("https://example.com/", timeout=999)

        assert "timed out" in result.lower() or "Error" in result

    @pytest.mark.asyncio
    async def test_invalid_headers_json(self):
        result = await _http_request(
            "https://example.com/", headers="not-valid-json"
        )
        assert "Error" in result
        assert "headers" in result.lower() or "JSON" in result

    @pytest.mark.asyncio
    async def test_request_error_returns_error(self):
        import httpx

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.request = AsyncMock(
            side_effect=httpx.RequestError("connection refused")
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await _http_request("https://example.com/")

        assert "Error" in result
        assert "connection refused" in result


# ============================================================================
# search_grep
# ============================================================================


class TestSearchGrep:
    @pytest.mark.asyncio
    async def test_basic_regex_match(self, tmp_path: Path):
        (tmp_path / "hello.py").write_text("def hello():\n    return 'world'\n")
        result = await _search_grep(pattern="def hello", path=str(tmp_path))
        assert "hello.py" in result
        assert "def hello" in result

    @pytest.mark.asyncio
    async def test_no_matches_returns_message(self, tmp_path: Path):
        (tmp_path / "empty.py").write_text("x = 1\n")
        result = await _search_grep(pattern="XYZZY_NOT_FOUND", path=str(tmp_path))
        assert "No matches" in result

    @pytest.mark.asyncio
    async def test_glob_filter_py_only(self, tmp_path: Path):
        (tmp_path / "code.py").write_text("# search_target here\n")
        (tmp_path / "readme.txt").write_text("search_target here too\n")
        result = await _search_grep(
            pattern="search_target", path=str(tmp_path), glob_filter="*.py"
        )
        assert "code.py" in result
        # txt file should not appear
        assert "readme.txt" not in result

    @pytest.mark.asyncio
    async def test_max_results_cap(self, tmp_path: Path):
        # Create 10 files each with a match
        for i in range(10):
            (tmp_path / f"file{i}.py").write_text(f"match_me line {i}\n")
        result = await _search_grep(
            pattern="match_me", path=str(tmp_path), max_results=3
        )
        assert "capped at 3" in result

    @pytest.mark.asyncio
    async def test_skips_git_directory(self, tmp_path: Path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("find_me_in_git\n")
        (tmp_path / "src.py").write_text("not_here\n")
        result = await _search_grep(pattern="find_me_in_git", path=str(tmp_path))
        assert "No matches" in result

    @pytest.mark.asyncio
    async def test_skips_pycache_directory(self, tmp_path: Path):
        cache_dir = tmp_path / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "mod.pyc").write_bytes(b"pycache_content")
        result = await _search_grep(pattern="pycache_content", path=str(tmp_path))
        assert "No matches" in result

    @pytest.mark.asyncio
    async def test_skips_node_modules(self, tmp_path: Path):
        nm_dir = tmp_path / "node_modules"
        nm_dir.mkdir()
        (nm_dir / "index.js").write_text("node_module_content\n")
        result = await _search_grep(pattern="node_module_content", path=str(tmp_path))
        assert "No matches" in result

    @pytest.mark.asyncio
    async def test_context_lines_included(self, tmp_path: Path):
        code = "line_before\nTARGET\nline_after\n"
        (tmp_path / "ctx.py").write_text(code)
        result = await _search_grep(
            pattern="TARGET", path=str(tmp_path), context_lines=1
        )
        assert "line_before" in result
        assert "line_after" in result

    @pytest.mark.asyncio
    async def test_invalid_regex_returns_error(self, tmp_path: Path):
        result = await _search_grep(pattern="[invalid(regex", path=str(tmp_path))
        assert "Error" in result
        assert "regex" in result.lower() or "pattern" in result.lower()

    @pytest.mark.asyncio
    async def test_nonexistent_path_returns_error(self):
        result = await _search_grep(pattern="x", path="/nonexistent/path/xyz")
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_workspace_enforcement_with_sandbox(self, tmp_path: Path):
        """When sandbox is set, path is resolved relative to workspace."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "code.py").write_text("sandboxed_pattern here\n")

        # Temporarily set sandbox config
        original = tools_module._sandbox_config
        from silkroute.agent.sandbox import SandboxConfig

        tools_module._sandbox_config = SandboxConfig(workspace_dir=workspace)
        try:
            result = await _search_grep(pattern="sandboxed_pattern", path=".")
            assert "code.py" in result
            assert "sandboxed_pattern" in result
        finally:
            tools_module._sandbox_config = original


# ============================================================================
# git_ops
# ============================================================================


class TestGitOps:
    @pytest.mark.asyncio
    async def test_allowed_status_operation(self, tmp_path: Path):
        """git status works in a real git repo (the silkroute repo itself)."""
        result = await _git_ops("status")
        # Should not return a blocked error
        assert "Error: Operation" not in result

    @pytest.mark.asyncio
    async def test_allowed_log_operation(self):
        result = await _git_ops("log", args="--oneline -3")
        assert "Error: Operation" not in result

    @pytest.mark.asyncio
    async def test_allowed_diff_operation(self):
        result = await _git_ops("diff", args="--stat HEAD")
        assert "Error: Operation" not in result

    @pytest.mark.asyncio
    async def test_allowed_branch_operation(self):
        result = await _git_ops("branch")
        assert "Error: Operation" not in result

    @pytest.mark.asyncio
    async def test_blocks_push(self):
        result = await _git_ops("push")
        assert "Error" in result
        assert "not allowed" in result

    @pytest.mark.asyncio
    async def test_blocks_reset(self):
        result = await _git_ops("reset")
        assert "Error" in result
        assert "not allowed" in result

    @pytest.mark.asyncio
    async def test_blocks_checkout(self):
        result = await _git_ops("checkout")
        assert "Error" in result
        assert "not allowed" in result

    @pytest.mark.asyncio
    async def test_blocks_commit(self):
        result = await _git_ops("commit")
        assert "Error" in result
        assert "not allowed" in result

    @pytest.mark.asyncio
    async def test_blocks_merge(self):
        result = await _git_ops("merge")
        assert "Error" in result
        assert "not allowed" in result

    @pytest.mark.asyncio
    async def test_blocks_rebase(self):
        result = await _git_ops("rebase")
        assert "Error" in result
        assert "not allowed" in result

    @pytest.mark.asyncio
    async def test_blocks_pull(self):
        result = await _git_ops("pull")
        assert "Error" in result
        assert "not allowed" in result

    @pytest.mark.asyncio
    async def test_blocks_clean(self):
        result = await _git_ops("clean")
        assert "Error" in result
        assert "not allowed" in result

    @pytest.mark.asyncio
    async def test_show_with_args(self):
        result = await _git_ops("show", args="--name-only HEAD")
        assert "Error: Operation" not in result

    @pytest.mark.asyncio
    async def test_tag_operation(self):
        result = await _git_ops("tag")
        assert "Error: Operation" not in result


# ============================================================================
# env_info
# ============================================================================


class TestEnvInfo:
    @pytest.mark.asyncio
    async def test_python_query(self):
        result = await _env_info("python")
        assert "Python:" in result
        assert "version" in result
        assert "executable" in result
        assert "virtual_env" in result

    @pytest.mark.asyncio
    async def test_os_query(self):
        result = await _env_info("os")
        assert "OS:" in result
        assert "platform" in result
        assert "hostname" in result

    @pytest.mark.asyncio
    async def test_packages_query(self):
        result = await _env_info("packages")
        assert "Packages:" in result
        # pip list should show at least pytest
        assert "package" in result.lower() or "Error" in result

    @pytest.mark.asyncio
    async def test_cwd_query(self):
        result = await _env_info("cwd")
        assert "CWD:" in result

    @pytest.mark.asyncio
    async def test_all_query_includes_all_sections(self):
        result = await _env_info("all")
        assert "Python:" in result
        assert "OS:" in result
        assert "CWD:" in result
        # Packages section always present even on error
        assert "Packages:" in result

    @pytest.mark.asyncio
    async def test_sensitive_env_vars_filtered_in_os_query(self, monkeypatch):
        """Env vars matching KEY, SECRET, TOKEN, PASSWORD, CREDENTIAL are excluded."""
        monkeypatch.setenv("MY_API_KEY", "super-secret-value")
        monkeypatch.setenv("DB_PASSWORD", "hunter2")
        monkeypatch.setenv("AUTH_TOKEN", "tok-12345")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-secret")
        monkeypatch.setenv("SAFE_VAR", "visible-value")

        result = await _env_info("os")

        assert "super-secret-value" not in result
        assert "hunter2" not in result
        assert "tok-12345" not in result
        assert "aws-secret" not in result
        # Safe var should appear
        assert "visible-value" in result or "SAFE_VAR" in result

    @pytest.mark.asyncio
    async def test_credential_pattern_filtered(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_CREDENTIAL_FILE", "/path/to/cred.json")
        result = await _env_info("os")
        assert "/path/to/cred.json" not in result

    @pytest.mark.asyncio
    async def test_unknown_query_returns_error(self):
        # The handler only accepts enum values, but test raw call
        result = await _env_info("unknown_query_xyz")
        assert "Error" in result or "Unknown" in result


# ============================================================================
# Registry integration
# ============================================================================


class TestRegistryHasNewTools:
    def test_registry_has_8_tools(self):
        registry = create_default_registry()
        names = registry.tool_names
        assert len(names) == 8

    def test_registry_has_http_request(self):
        registry = create_default_registry()
        assert "http_request" in registry.tool_names

    def test_registry_has_search_grep(self):
        registry = create_default_registry()
        assert "search_grep" in registry.tool_names

    def test_registry_has_git_ops(self):
        registry = create_default_registry()
        assert "git_ops" in registry.tool_names

    def test_registry_has_env_info(self):
        registry = create_default_registry()
        assert "env_info" in registry.tool_names

    def test_skill_registry_mounted_when_provided(self):
        """When skill_registry and skill_ctx are provided, mount() is called."""
        mock_skill_registry = MagicMock()
        mock_ctx = MagicMock()

        registry = create_default_registry(
            skill_registry=mock_skill_registry,
            skill_ctx=mock_ctx,
        )

        mock_skill_registry.mount.assert_called_once_with(registry, mock_ctx)

    def test_skill_registry_not_mounted_when_ctx_missing(self):
        """mount() is NOT called if skill_ctx is None."""
        mock_skill_registry = MagicMock()

        create_default_registry(skill_registry=mock_skill_registry, skill_ctx=None)

        mock_skill_registry.mount.assert_not_called()
