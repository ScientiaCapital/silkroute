"""Regression tests for the security-audit findings.

Each test reproduces a concrete bypass input from the audit:
redirect-based SSRF, file-tool path escapes, git_ops write/exfil arguments,
unsafe `silkroute mcp serve` exports, shell env leakage + memory cap, and
supervisor endpoints reachable in demo mode. No test touches the network.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from silkroute.agent import tools as tools_module
from silkroute.agent.sandbox import SandboxConfig, build_sandbox_env
from silkroute.agent.tools import _git_ops, _http_request, create_default_registry
from silkroute.mantis.skills.builtin.http_skill import _http_request_handler
from silkroute.network.ssrf import SSRFBlockedError, SSRFPinnedTransport, guarded_request

_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _client_factory(handler, seen: list[str]):  # noqa: ANN001, ANN202
    """Return a patched AsyncClient constructor backed by a MockTransport."""

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return handler(request)

    def factory(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        assert kwargs.get("follow_redirects") is False, "redirects must be manual"
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(recording))

    return factory


def _redirect_to(target: str):  # noqa: ANN202
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "public.example.com":
            return httpx.Response(302, headers={"location": target})
        return httpx.Response(200, text="SECRET-METADATA")

    return handler


# ============================================================================
# 2. Redirects — every hop is SSRF-checked
# ============================================================================


class TestRedirectSSRF:
    @pytest.mark.parametrize(
        "target",
        [
            "http://169.254.169.254/latest/meta-data/",
            "http://[::ffff:169.254.169.254]/",
            "http://127.0.0.1:8787/",
            "http://100.100.100.200/",
        ],
    )
    async def test_tool_refuses_redirect_to_internal(self, target: str) -> None:
        seen: list[str] = []
        with patch("httpx.AsyncClient", _client_factory(_redirect_to(target), seen)):
            result = await _http_request("http://public.example.com/start")
        assert "SSRF" in result and "Blocked" in result
        assert "SECRET-METADATA" not in result
        assert seen == ["http://public.example.com/start"]

    async def test_skill_refuses_redirect_to_metadata(self) -> None:
        seen: list[str] = []
        handler = _redirect_to("http://169.254.169.254/")
        with patch("httpx.AsyncClient", _client_factory(handler, seen)):
            result = await _http_request_handler(url="http://public.example.com/start")
        assert result.startswith("Error:") and "Blocked" in result
        assert "SECRET-METADATA" not in result
        assert seen == ["http://public.example.com/start"]

    async def test_relative_redirect_to_public_is_followed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/start":
                return httpx.Response(301, headers={"location": "/final"})
            return httpx.Response(200, text="landed")

        seen: list[str] = []
        with patch("httpx.AsyncClient", _client_factory(handler, seen)):
            result = await _http_request("http://public.example.com/start")
        assert "Status: 200" in result and "landed" in result
        assert seen[-1] == "http://public.example.com/final"

    async def test_redirect_loop_capped(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": "/again"})

        seen: list[str] = []
        with patch("httpx.AsyncClient", _client_factory(handler, seen)):
            result = await _http_request("http://public.example.com/start")
        assert "Error" in result and "redirect" in result.lower()
        assert len(seen) == 6  # initial request + 5 redirects

    async def test_cross_origin_redirect_drops_credentials(self) -> None:
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            if request.url.host == "a.example.com":
                return httpx.Response(302, headers={"location": "http://b.example.com/"})
            return httpx.Response(200)

        async with _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler)) as client:
            await guarded_request(
                client, "GET", "http://a.example.com/", headers={"Authorization": "Bearer x"}
            )
        assert "authorization" in captured[0].headers
        assert "authorization" not in captured[1].headers


class TestPinnedTransport:
    async def test_connects_to_checked_ip_with_original_host_and_sni(self) -> None:
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200)

        transport = SSRFPinnedTransport(httpx.MockTransport(handler))
        async with _REAL_ASYNC_CLIENT(transport=transport) as client:
            await client.get("https://example.com/path")
        req = captured[0]
        assert req.url.host == "93.184.216.34"  # conftest resolver
        assert req.headers["host"] == "example.com"
        assert req.extensions["sni_hostname"] == "example.com"

    async def test_rebinding_to_private_at_connect_time_is_refused(self) -> None:
        """Even if the pre-check passed, the transport re-resolves and refuses."""
        import socket

        def private(host, port, *a, **k):  # noqa: ANN001, ANN002, ANN003, ANN202
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", port or 0))]

        inner = AsyncMock()
        transport = SSRFPinnedTransport(inner)
        with patch("silkroute.network.ssrf._getaddrinfo", private):
            async with _REAL_ASYNC_CLIENT(transport=transport) as client:
                with pytest.raises(SSRFBlockedError):
                    await client.get("http://rebind.example.com/")
        inner.handle_async_request.assert_not_called()


# ============================================================================
# 3. File tools confined to the workspace root
# ============================================================================


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "notes.txt").write_text("inside")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("TOP-SECRET")
    (ws / "escape").symlink_to(outside / "secret.txt")
    (ws / "escape_dir").symlink_to(outside, target_is_directory=True)
    return ws


class TestFileToolConfinement:
    async def test_relative_path_works(self, workspace: Path) -> None:
        registry = create_default_registry(workspace_dir=str(workspace))
        assert await registry.execute("read_file", {"path": "notes.txt"}) == "inside"
        res = await registry.execute("write_file", {"path": "sub/new.txt", "content": "x"})
        assert "Successfully wrote" in res
        assert (workspace / "sub" / "new.txt").read_text() == "x"
        assert "notes.txt" in await registry.execute("list_directory", {"path": "."})

    @pytest.mark.parametrize("tool", ["read_file", "list_directory"])
    async def test_dotdot_traversal_refused(self, workspace: Path, tool: str) -> None:
        registry = create_default_registry(workspace_dir=str(workspace))
        res = await registry.execute(tool, {"path": "../../etc/passwd"})
        assert "outside the workspace" in res

    async def test_dotdot_write_refused(self, workspace: Path) -> None:
        registry = create_default_registry(workspace_dir=str(workspace))
        res = await registry.execute("write_file", {"path": "../evil.txt", "content": "x"})
        assert "outside the workspace" in res
        assert not (workspace.parent / "evil.txt").exists()

    async def test_absolute_path_outside_refused(self, workspace: Path) -> None:
        registry = create_default_registry(workspace_dir=str(workspace))
        secret = str(workspace.parent / "outside" / "secret.txt")
        for tool, args in [
            ("read_file", {"path": secret}),
            ("write_file", {"path": secret, "content": "pwned"}),
            ("list_directory", {"path": str(workspace.parent / "outside")}),
        ]:
            res = await registry.execute(tool, args)
            assert "outside the workspace" in res, tool
        assert (workspace.parent / "outside" / "secret.txt").read_text() == "TOP-SECRET"

    async def test_symlink_pointing_outside_refused(self, workspace: Path) -> None:
        registry = create_default_registry(workspace_dir=str(workspace))
        res = await registry.execute("read_file", {"path": "escape"})
        assert "outside the workspace" in res and "TOP-SECRET" not in res
        res = await registry.execute("write_file", {"path": "escape", "content": "pwned"})
        assert "outside the workspace" in res
        res = await registry.execute("list_directory", {"path": "escape_dir"})
        assert "outside the workspace" in res
        assert (workspace.parent / "outside" / "secret.txt").read_text() == "TOP-SECRET"

    async def test_no_workspace_confines_to_cwd(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(workspace)
        registry = create_default_registry()
        assert await registry.execute("read_file", {"path": "notes.txt"}) == "inside"
        res = await registry.execute("read_file", {"path": "/etc/passwd"})
        assert "outside the workspace" in res

    async def test_search_grep_absolute_escape_refused(self, workspace: Path) -> None:
        registry = create_default_registry(workspace_dir=str(workspace))
        res = await registry.execute(
            "search_grep", {"pattern": "TOP", "path": str(workspace.parent / "outside")}
        )
        assert "outside the workspace" in res


# ============================================================================
# 4. git_ops argument allowlist
# ============================================================================


class TestGitOpsAllowlist:
    @pytest.mark.parametrize(
        ("operation", "args"),
        [
            ("diff", "--output=/tmp/pwn"),
            ("diff", "--output /tmp/pwn"),
            ("diff", "--outp=/tmp/pwn"),
            ("log", "-o /tmp/pwn"),
            ("show", "-o/tmp/pwn HEAD"),
            ("log", "--output=/tmp/pwn -p"),
            ("diff", "--no-index /etc/passwd /dev/null"),
            ("diff", "--ext-diff"),
            ("branch", "-D main"),
            ("branch", "-d main"),
            ("branch", "--delete main"),
            ("branch", "-m old new"),
            ("branch", "newbranch"),
            ("branch", "--set-upstream-to=origin/main"),
            ("remote", "set-url origin https://evil.example/x.git"),
            ("remote", "add evil https://evil.example/x.git"),
            ("remote", "remove origin"),
            ("tag", "v9.9.9"),
            ("tag", "-d v1.0"),
            ("push", ""),
            ("push", "--force origin main"),
            ("reset", "--hard HEAD~1"),
            ("config", "core.hooksPath /tmp/x"),
        ],
    )
    async def test_refused(self, operation: str, args: str) -> None:
        with patch("silkroute.agent.tools.asyncio.create_subprocess_exec") as spawn:
            result = await _git_ops(operation, args=args)
        assert result.startswith("Error"), result
        spawn.assert_not_called()

    @pytest.mark.parametrize(
        ("operation", "args"),
        [
            ("status", ""),
            ("log", "--oneline -3"),
            ("diff", "--stat HEAD"),
            ("show", "--name-only HEAD"),
            ("branch", ""),
            ("branch", "-a -v"),
            ("branch", "--list feat/*"),
            ("remote", "-v"),
            ("remote", "get-url origin"),
            ("tag", "--list v1.*"),
        ],
    )
    async def test_read_only_allowed(self, operation: str, args: str) -> None:
        proc = AsyncMock()
        proc.communicate = AsyncMock(return_value=(b"ok", b""))
        proc.returncode = 0
        with patch(
            "silkroute.agent.tools.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)
        ) as spawn:
            result = await _git_ops(operation, args=args)
        assert result == "ok"
        assert spawn.call_args.args[:2] == ("git", operation)


# ============================================================================
# 5. `silkroute mcp serve` requires --workspace for shell/write exports
# ============================================================================


class TestMcpServeWorkspaceGuard:
    @pytest.mark.parametrize(
        "argv",
        [
            ["mcp", "serve", "--all"],
            ["mcp", "serve", "--allow", "shell_exec"],
            ["mcp", "serve", "--allow", "write_file"],
        ],
    )
    def test_refuses_without_workspace(self, argv: list[str]) -> None:
        from silkroute.cli import main

        with patch("silkroute.mcp_bridge.server.serve_stdio", new=AsyncMock()) as serve:
            result = CliRunner().invoke(main, argv)
        assert result.exit_code != 0
        assert "--workspace" in result.output
        serve.assert_not_called()

    def test_starts_with_workspace(self, tmp_path: Path) -> None:
        from silkroute.cli import main

        with patch("silkroute.mcp_bridge.server.serve_stdio", new=AsyncMock()) as serve:
            result = CliRunner().invoke(
                main, ["mcp", "serve", "--allow", "shell_exec", "--workspace", str(tmp_path)]
            )
        assert result.exit_code == 0, result.output
        serve.assert_awaited_once()

    def test_read_only_default_needs_no_workspace(self) -> None:
        from silkroute.cli import main

        with patch("silkroute.mcp_bridge.server.serve_stdio", new=AsyncMock()) as serve:
            result = CliRunner().invoke(main, ["mcp", "serve"])
        assert result.exit_code == 0, result.output
        serve.assert_awaited_once()


# ============================================================================
# 6. Shell: scrubbed environment + memory cap
# ============================================================================


class TestShellEnvironment:
    @pytest.mark.parametrize(
        "var",
        [
            "FAKE_API_KEY",
            "MY_TOKEN",
            "DB_PASSWORD",
            "SOME_SECRET",
            "SILKROUTE_OPENROUTER_API_KEY",
            "SILKROUTE_API_KEY",
            "OPENROUTER_BASE",
            "ANTHROPIC_BASE_URL",
        ],
    )
    async def test_printenv_cannot_see_secret(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, var: str
    ) -> None:
        monkeypatch.setenv(var, "sk-should-not-leak")
        registry = create_default_registry(workspace_dir=str(tmp_path))
        result = await registry.execute("shell_exec", {"command": "printenv"})
        assert "sk-should-not-leak" not in result
        assert var not in result

    async def test_printenv_cannot_see_secret_without_workspace(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FAKE_API_KEY", "sk-should-not-leak")
        registry = create_default_registry()
        result = await registry.execute("shell_exec", {"command": "printenv"})
        assert "sk-should-not-leak" not in result

    async def test_path_and_home_kept(self, tmp_path: Path) -> None:
        registry = create_default_registry(workspace_dir=str(tmp_path))
        result = await registry.execute("shell_exec", {"command": "printenv PATH HOME"})
        assert os.environ["PATH"] in result

    def test_explicit_allowlist_still_filters_credentials(self) -> None:
        config = SandboxConfig(
            workspace_dir=Path("."), env_allowlist=frozenset({"EXTRA", "EXTRA_TOKEN"})
        )
        env = build_sandbox_env(
            config, source={"EXTRA": "1", "EXTRA_TOKEN": "t", "PATH": "/bin", "OTHER": "x"}
        )
        assert env == {"EXTRA": "1", "PATH": "/bin"}

    @pytest.mark.skipif(not sys.platform.startswith("linux"), reason="RLIMIT_AS enforced on Linux")
    async def test_memory_cap_applied(self, tmp_path: Path) -> None:
        create_default_registry(workspace_dir=str(tmp_path))
        tools_module._sandbox_config.max_memory_mb = 256  # type: ignore[union-attr]
        result = await tools_module._shell_exec("ulimit -v")
        assert result.strip() == str(256 * 1024)


# ============================================================================
# 7. Supervisor endpoints blocked in demo mode
# ============================================================================


class TestSupervisorDemoMode:
    def _client(self, demo_mode: bool) -> TestClient:
        from silkroute.api import deps
        from silkroute.api.app import create_app
        from silkroute.config.settings import ApiConfig, ProviderConfig, SilkRouteSettings

        settings = SilkRouteSettings(
            providers=ProviderConfig(ollama_enabled=True),
            api=ApiConfig(api_key="test-secret", demo_mode=demo_mode),
        )
        app = create_app(settings)
        app.dependency_overrides[deps.get_settings] = lambda: settings
        app.dependency_overrides[deps.get_db_pool] = lambda: None
        return TestClient(app, raise_server_exceptions=False)

    @patch("silkroute.api.routes.supervisor.SupervisorRuntime")
    def test_create_blocked(self, mock_rt_cls) -> None:  # noqa: ANN001
        resp = self._client(True).post(
            "/supervisor/sessions",
            json={"project_id": "p", "description": "d", "steps": [{"name": "s"}]},
            headers={"Authorization": "Bearer test-secret"},
        )
        assert resp.status_code == 403
        mock_rt_cls.assert_not_called()

    @patch("silkroute.api.routes.supervisor.SupervisorRuntime")
    def test_resume_blocked(self, mock_rt_cls) -> None:  # noqa: ANN001
        resp = self._client(True).post(
            "/supervisor/sessions/abc/resume",
            headers={"Authorization": "Bearer test-secret"},
        )
        assert resp.status_code == 403
        mock_rt_cls.assert_not_called()

    def test_env_var_enables_block(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SILKROUTE_API_DEMO_MODE", "true")
        from silkroute.config.settings import ApiConfig

        assert ApiConfig().demo_mode is True

    @patch("silkroute.api.routes.supervisor.SupervisorRuntime")
    def test_resume_allowed_when_not_demo(self, mock_rt_cls) -> None:  # noqa: ANN001
        from silkroute.mantis.runtime.interface import AgentResult

        mock_rt_cls.return_value.resume_session = AsyncMock(
            return_value=AgentResult(status="completed", cost_usd=0.0)
        )
        resp = self._client(False).post(
            "/supervisor/sessions/abc/resume",
            headers={"Authorization": "Bearer test-secret"},
        )
        assert resp.status_code == 200


class TestGrepSymlinkEscape:
    async def test_symlinked_file_outside_root_not_read(self, workspace: Path) -> None:
        registry = create_default_registry(workspace_dir=str(workspace))
        res = await registry.execute("search_grep", {"pattern": "TOP-SECRET", "path": "."})
        assert "No matches" in res


class TestMcpServeDefaultConfinement:
    def test_default_serve_confines_tools_to_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from silkroute.cli import main

        monkeypatch.chdir(tmp_path)
        with patch("silkroute.mcp_bridge.server.serve_stdio", new=AsyncMock()):
            result = CliRunner().invoke(main, ["mcp", "serve"])
        assert result.exit_code == 0, result.output
        assert tools_module._sandbox_config is not None
        assert tools_module._sandbox_config.workspace_dir == tmp_path.resolve()
