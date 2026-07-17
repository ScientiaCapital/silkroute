"""Expose SilkRoute's ToolRegistry *as* an MCP server — the inverse of client.py.

``client.py`` turns external MCP tools into ``ToolSpec``s so the agent loop can
call them. This module turns ``ToolSpec``s back into MCP tools so other agents or
MCP clients can drive SilkRoute's curated toolset. That is the "control plane"
role: SilkRoute composes N upstream MCP servers plus its own built-ins, then
re-serves a curated, allowlisted subset.

Security: the default export policy is READ-ONLY. Exposing ``shell_exec`` /
``write_file`` / ``http_request`` over MCP would make this a remote code-exec /
SSRF surface, so those are opt-in only via an explicit ``export_allowlist``.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

import structlog
from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

if TYPE_CHECKING:
    from silkroute.agent.tools import ToolRegistry, ToolSpec

log = structlog.get_logger()

# Conservative default: read-only inspection tools only.
DEFAULT_EXPORT_ALLOWLIST: frozenset[str] = frozenset(
    {"read_file", "list_directory", "search_grep", "git_ops", "env_info"}
)


def _resolve_allowlist(export_allowlist: Iterable[str] | None) -> frozenset[str]:
    """None → the safe read-only default; otherwise the caller's exact set."""
    if export_allowlist is None:
        return DEFAULT_EXPORT_ALLOWLIST
    return frozenset(export_allowlist)


def select_exported_specs(
    registry: ToolRegistry, export_allowlist: Iterable[str] | None
) -> list[ToolSpec]:
    """Return the ToolSpecs to expose, filtered by the allowlist.

    ``export_allowlist=None`` uses :data:`DEFAULT_EXPORT_ALLOWLIST`. Pass an empty
    iterable to export nothing, or a custom set to opt specific tools in. Names in
    the allowlist that aren't registered are silently ignored. Order follows the
    registry's registration order.
    """
    allow = _resolve_allowlist(export_allowlist)
    return [
        spec
        for name in registry.tool_names
        if name in allow and (spec := registry.get(name)) is not None
    ]


def spec_to_mcp_tool(spec: ToolSpec) -> types.Tool:
    """Map a ToolSpec to an MCP Tool (the inverse of client._build_tool_spec)."""
    return types.Tool(
        name=spec.name,
        description=spec.description,
        inputSchema=spec.parameters,
    )


async def dispatch_tool(
    registry: ToolRegistry,
    name: str,
    arguments: dict[str, Any],
    export_allowlist: Iterable[str] | None,
) -> str:
    """Execute a tool call, enforcing the export allowlist first.

    A non-exported tool is refused WITHOUT executing — the allowlist is the
    security boundary, not just a discovery filter.
    """
    allow = _resolve_allowlist(export_allowlist)
    if name not in allow:
        return f"Error: tool '{name}' is not exported by this MCP server"
    return await registry.execute(name, arguments)


def build_mcp_server(
    registry: ToolRegistry,
    *,
    name: str = "silkroute",
    export_allowlist: Iterable[str] | None = None,
) -> Server:
    """Build an MCP ``Server`` backed by a ToolRegistry."""
    server: Server = Server(name)

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        return [spec_to_mcp_tool(s) for s in select_exported_specs(registry, export_allowlist)]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        text = await dispatch_tool(registry, name, arguments or {}, export_allowlist)
        return [types.TextContent(type="text", text=text)]

    return server


async def serve_stdio(
    registry: ToolRegistry,
    *,
    name: str = "silkroute",
    export_allowlist: Iterable[str] | None = None,
) -> None:
    """Run the MCP server over stdio until the client disconnects."""
    server = build_mcp_server(registry, name=name, export_allowlist=export_allowlist)
    exported = [s.name for s in select_exported_specs(registry, export_allowlist)]
    # stdout is the MCP protocol channel over stdio — logging MUST go to stderr,
    # or the very first log line corrupts the client's JSON-RPC handshake.
    stderr_log = structlog.wrap_logger(structlog.PrintLogger(file=sys.stderr))
    stderr_log.info("mcp_server_starting", name=name, exported=exported)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
