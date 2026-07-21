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


class TestOpenAVPreset:
    def test_openav_preset_when_enabled(self) -> None:
        devices = '[{"alias":"room-cam","host":"192.168.8.11","kind":"ec20"}]'
        cfg = MCPConfig(
            openav_enabled=True,
            openav_devices=devices,
            openav_ec20_url="http://localhost:8082",
        )
        servers = cfg.enabled_servers()
        assert len(servers) == 1
        s = servers[0]
        assert s.name == "openav"
        assert s.command == cfg.openav_command
        assert s.tool_allowlist == cfg.openav_tool_allowlist
        # Only set env vars are forwarded (empty ones dropped).
        assert s.env == {
            "OPENAV_DEVICES": devices,
            "OPENAV_EC20_URL": "http://localhost:8082",
        }

    def test_openav_read_only_by_default(self) -> None:
        # Mutating tools are opt-in: default launches the server with --read-only.
        cfg = MCPConfig(openav_enabled=True)
        (s,) = cfg.enabled_servers()
        assert s.args == ["-m", "openav_mcp", "--read-only"]

    def test_openav_mutating_opt_in_drops_read_only(self) -> None:
        cfg = MCPConfig(openav_enabled=True, openav_mutating=True)
        (s,) = cfg.enabled_servers()
        assert s.args == ["-m", "openav_mcp"]
        assert "--read-only" not in s.args

    def test_openav_disabled_omits_preset(self) -> None:
        assert all(s.name != "openav" for s in MCPConfig().enabled_servers())

    def test_preset_order_epiphan_openav_explicit(self) -> None:
        extra = MCPServerConfig(name="weather", command="node")
        cfg = MCPConfig(epiphan_enabled=True, openav_enabled=True, servers=[extra])
        assert [s.name for s in cfg.enabled_servers()] == ["epiphan", "openav", "weather"]

    def test_tracking_not_in_default_allowlist(self) -> None:
        # ec20_tracking is deferred (not VISCA-controllable) — keep it out until
        # the CGI path lands.
        assert "ec20_tracking" not in MCPConfig().openav_tool_allowlist

    def test_uncalibrated_ptz_not_in_default_allowlist(self) -> None:
        # ec20_ptz does absolute-degree moves through PLACEHOLDER calibration
        # constants — excluded until on-hardware calibration; jog + presets are
        # the calibration-independent movement verbs.
        allowlist = MCPConfig().openav_tool_allowlist
        assert "ec20_ptz" not in allowlist
        assert "ec20_jog" in allowlist
        assert "ec20_preset_save" in allowlist


class TestMCPServerConfigDefaults:
    def test_defaults(self) -> None:
        s = MCPServerConfig(name="x")
        assert s.command == "python"
        assert s.args == []
        assert s.env == {}
        assert s.tool_allowlist == []
