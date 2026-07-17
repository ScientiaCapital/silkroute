"""Tests for the generalized MCPConfig — N upstream MCP servers.

The bridge core (connect_mcp_server) has always been server-agnostic; MCPConfig
was epiphan-only. enabled_servers() normalizes the epiphan back-compat preset
plus any explicitly configured servers into one list the loop iterates.
"""

from __future__ import annotations

from silkroute.config.settings import MCPConfig, MCPServerConfig


class TestEnabledServers:
    def test_nothing_enabled_is_empty(self) -> None:
        assert MCPConfig().enabled_servers() == []

    def test_epiphan_preset_when_enabled(self) -> None:
        cfg = MCPConfig(
            epiphan_enabled=True,
            epiphan_pearl_devices="10.0.0.5",
        )
        servers = cfg.enabled_servers()
        assert len(servers) == 1
        s = servers[0]
        assert s.name == "epiphan"
        assert s.command == cfg.epiphan_command
        assert s.args == cfg.epiphan_args
        assert s.tool_allowlist == cfg.epiphan_tool_allowlist
        # Only set Pearl env vars are forwarded (empty ones dropped).
        assert s.env == {"PEARL_DEVICES": "10.0.0.5"}

    def test_epiphan_disabled_omits_preset(self) -> None:
        cfg = MCPConfig(epiphan_enabled=False)
        assert all(s.name != "epiphan" for s in cfg.enabled_servers())

    def test_explicit_servers_included(self) -> None:
        extra = MCPServerConfig(name="weather", command="node", args=["weather.js"])
        cfg = MCPConfig(servers=[extra])
        servers = cfg.enabled_servers()
        assert [s.name for s in servers] == ["weather"]

    def test_epiphan_preset_first_then_explicit(self) -> None:
        extra = MCPServerConfig(name="weather", command="node")
        cfg = MCPConfig(epiphan_enabled=True, servers=[extra])
        assert [s.name for s in cfg.enabled_servers()] == ["epiphan", "weather"]


class TestMCPServerConfigDefaults:
    def test_defaults(self) -> None:
        s = MCPServerConfig(name="x")
        assert s.command == "python"
        assert s.args == []
        assert s.env == {}
        assert s.tool_allowlist == []
