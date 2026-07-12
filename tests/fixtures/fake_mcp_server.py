"""Tiny stdio MCP server used only by tests/test_mcp_bridge.py.

Exposes three tools: a normal echo, a tool that raises (to exercise the
isError path), and a decoy meant to be excluded by an allowlist.
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("fake-server-for-tests")


@mcp.tool()
def echo(message: str) -> str:
    """Echo the given message back."""
    return f"echo: {message}"


@mcp.tool()
def always_fails() -> str:
    """A tool that always raises, to exercise the MCP isError path."""
    raise RuntimeError("intentional failure for testing")


@mcp.tool()
def not_allowlisted() -> str:
    """A tool that should be excluded when a tool_allowlist is supplied."""
    return "should not be reachable"


if __name__ == "__main__":
    mcp.run()
