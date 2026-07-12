"""Generic MCP stdio client bridge.

Spawns any MCP-compatible server as a subprocess, discovers its tool catalog,
and registers an allowlisted subset into a ``ToolRegistry`` so the ReAct loop
can call them exactly like a built-in tool. Protocol-generic by design — the
epiphan-mcp-server-specific wiring (Pearl env vars, tool allowlist) lives in
the demo script and ``MCPConfig``, not here.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

import structlog
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from silkroute.agent.tools import ToolSpec

if TYPE_CHECKING:
    from mcp.types import Tool

    from silkroute.agent.tools import ToolRegistry

log = structlog.get_logger()


async def connect_mcp_server(
    registry: ToolRegistry,
    *,
    command: str,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    tool_allowlist: list[str] | None = None,
) -> contextlib.AsyncExitStack | None:
    """Connect to an MCP server over stdio and register its tools.

    Spawns ``command args`` as a subprocess speaking the MCP stdio protocol
    (``env`` is merged on top of the subprocess's default environment, not
    replacing it — PATH/HOME etc. are preserved), discovers its tool catalog
    via ``list_tools()``, and registers an allowlisted subset (or everything,
    if ``tool_allowlist`` is None) into *registry*.

    Returns the ``AsyncExitStack`` owning the subprocess + session — the
    caller must ``await stack.aclose()`` when done. Returns None if the
    connection failed; callers should treat that as non-fatal and continue
    with the registry's existing tools rather than crash.
    """
    stack = contextlib.AsyncExitStack()
    try:
        params = StdioServerParameters(command=command, args=args or [], env=env or {})
        read_stream, write_stream = await stack.enter_async_context(stdio_client(params))
        session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
        await session.initialize()

        listed = await session.list_tools()
        tools = listed.tools
        if tool_allowlist is not None:
            allowed = set(tool_allowlist)
            tools = [t for t in tools if t.name in allowed]

        for tool in tools:
            registry.register(_build_tool_spec(session, tool))

        log.info(
            "mcp_bridge_connected",
            command=command,
            tools_discovered=len(listed.tools),
            tools_registered=len(tools),
        )
        return stack
    except Exception as exc:
        log.warning("mcp_bridge_connect_failed", command=command, error=str(exc))
        await stack.aclose()
        return None


def _build_tool_spec(session: ClientSession, tool: Tool) -> ToolSpec:
    """Build a ToolSpec whose handler proxies to a single MCP server tool."""

    async def _handler(**kwargs: Any) -> str:  # noqa: ANN401
        result = await session.call_tool(tool.name, kwargs)
        text = "\n".join(block.text for block in result.content if hasattr(block, "text"))
        if result.isError:
            return text if text.startswith("Error") else f"Error: {text}"
        return text

    return ToolSpec(
        name=tool.name,
        description=tool.description or f"MCP tool '{tool.name}'",
        parameters=tool.inputSchema,
        handler=_handler,
    )
