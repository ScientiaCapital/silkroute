"""Tool registry and built-in tools for the ReAct agent.

Provides a registry for tool specifications and 4 built-in tools:
shell_exec, read_file, write_file, list_directory.

Shell execution is sandboxed via agent.sandbox — see that module for
blocklist patterns, workspace enforcement, and resource limits.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from silkroute.agent.sandbox import SandboxConfig, validate_command

log = structlog.get_logger()

# Module-level sandbox config — set by create_default_registry()
_sandbox_config: SandboxConfig | None = None


@dataclass
class ToolSpec:
    """Definition of a tool the agent can invoke."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema
    handler: Callable[..., Awaitable[str]]


class ToolRegistry:
    """Registry of available tools with execution support."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, tool: ToolSpec) -> None:
        """Register a tool specification."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolSpec | None:
        """Look up a tool by name."""
        return self._tools.get(name)

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def to_openai_tools(self) -> list[dict[str, Any]]:
        """Convert registry to OpenAI-compatible tool definitions for litellm."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self._tools.values()
        ]

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """Execute a registered tool by name with parsed arguments."""
        tool = self._tools.get(name)
        if not tool:
            return f"Error: Unknown tool '{name}'. Available: {', '.join(self._tools)}"
        try:
            return await tool.handler(**arguments)
        except TypeError as e:
            return f"Error: Invalid arguments for '{name}': {e}"
        except Exception as e:
            log.error("tool_execution_error", tool=name, error=str(e))
            return f"Error executing '{name}': {e}"


def parse_tool_arguments(raw: str | dict) -> dict[str, Any]:
    """Parse tool call arguments with fallbacks for malformed Chinese LLM output.

    Handles: raw JSON, markdown-fenced JSON, single-quoted dicts, trailing commas.
    """
    if isinstance(raw, dict):
        return raw

    raw = raw.strip()
    if not raw:
        return {}

    # Attempt 1: Direct JSON parse
    try:
        result = json.loads(raw)
        return result if isinstance(result, dict) else {}
    except json.JSONDecodeError:
        pass

    # Attempt 2: Strip markdown code fences (```json ... ```)
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", raw, re.DOTALL)
    if fence_match:
        try:
            result = json.loads(fence_match.group(1).strip())
            return result if isinstance(result, dict) else {}
        except json.JSONDecodeError:
            pass

    # Attempt 3: Repair single quotes → double quotes, strip trailing commas
    repaired = raw.replace("'", '"')
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    try:
        result = json.loads(repaired)
        return result if isinstance(result, dict) else {}
    except json.JSONDecodeError:
        log.warning("unparseable_tool_arguments", raw=raw[:200])
        return {}


# ============================================================================
# Built-in tools
# ============================================================================


async def _shell_exec(command: str, timeout: int = 30) -> str:
    """Execute a shell command with timeout and sandbox validation.

    All commands pass through the sandbox before execution:
    - Blocklist check (rejects destructive/exfiltration patterns)
    - Working directory enforcement (confines to workspace)
    - Resource limits (memory cap via ulimit)

    NOTE: This uses create_subprocess_shell intentionally — the agent
    requires shell features (pipes, globbing, env vars). The sandbox
    layer validates commands before they reach the shell.
    """
    timeout = min(max(timeout, 1), 120)  # Clamp 1-120s

    # Sandbox validation
    if _sandbox_config is not None:
        violation = validate_command(command, _sandbox_config)
        if violation is not None:
            log.warning(
                "shell_exec_blocked",
                command=command[:200],
                reason=violation.reason,
            )
            return f"Error: Command blocked by sandbox — {violation.reason}"

    try:
        # Build execution kwargs
        kwargs: dict[str, Any] = {
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
        }

        # Set working directory if sandbox is configured
        if _sandbox_config is not None:
            kwargs["cwd"] = str(_sandbox_config.workspace_dir)

        proc = await asyncio.create_subprocess_shell(command, **kwargs)
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = stdout.decode(errors="replace")
        if proc.returncode != 0:
            err = stderr.decode(errors="replace")
            if err:
                output += f"\n[exit code: {proc.returncode}]\n{err}"
            else:
                output += f"\n[exit code: {proc.returncode}]"
        if len(output) > 10_000:
            output = output[:10_000] + f"\n... (truncated, {len(output)} chars total)"
        return output
    except TimeoutError:
        return f"Error: Command timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"


async def _read_file(path: str, start_line: int = 0, end_line: int = 0) -> str:
    """Read file contents, optionally a specific line range."""
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return f"Error: File not found: {path}"
        if not p.is_file():
            return f"Error: Not a file: {path}"
        text = p.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        if start_line > 0 or end_line > 0:
            start = max(start_line - 1, 0)  # Convert to 0-indexed
            end = end_line if end_line > 0 else len(lines)
            lines = lines[start:end]
        content = "\n".join(lines)
        if len(content) > 20_000:
            content = content[:20_000] + f"\n... (truncated, {len(content)} chars total)"
        return content
    except Exception as e:
        return f"Error reading file: {e}"


async def _write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent directories if needed."""
    try:
        p = Path(path).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} bytes to {p}"
    except Exception as e:
        return f"Error writing file: {e}"


async def _list_directory(path: str = ".") -> str:
    """List files and directories at the given path."""
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return f"Error: Directory not found: {path}"
        if not p.is_dir():
            return f"Error: Not a directory: {path}"
        entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        lines = []
        for entry in entries[:200]:
            prefix = "d " if entry.is_dir() else "f "
            size = ""
            if entry.is_file():
                with contextlib.suppress(OSError):
                    size = f"  ({entry.stat().st_size:,} bytes)"
            lines.append(f"{prefix}{entry.name}{size}")
        result = "\n".join(lines)
        if len(entries) > 200:
            result += f"\n... ({len(entries)} total entries, showing first 200)"
        return result
    except Exception as e:
        return f"Error listing directory: {e}"


def create_default_registry(workspace_dir: str | None = None) -> ToolRegistry:
    """Create a registry with the 4 built-in tools.

    If workspace_dir is provided, shell_exec commands are sandboxed:
    blocklist validation, working directory enforcement, and resource limits.
    """
    global _sandbox_config  # noqa: PLW0603

    if workspace_dir is not None:
        _sandbox_config = SandboxConfig(workspace_dir=Path(workspace_dir).resolve())
    else:
        _sandbox_config = None

    registry = ToolRegistry()

    registry.register(ToolSpec(
        name="shell_exec",
        description=(
            "Execute a shell command and return its output. "
            "Use for running scripts, git commands, build tools, etc."
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (1-120, default 30)",
                    "default": 30,
                },
            },
            "required": ["command"],
        },
        handler=_shell_exec,
    ))

    registry.register(ToolSpec(
        name="read_file",
        description=(
            "Read the contents of a file. "
            "Optionally specify start_line and end_line for a range."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to read",
                },
                "start_line": {
                    "type": "integer",
                    "description": "First line to read (1-indexed, optional)",
                    "default": 0,
                },
                "end_line": {
                    "type": "integer",
                    "description": "Last line to read (inclusive, optional)",
                    "default": 0,
                },
            },
            "required": ["path"],
        },
        handler=_read_file,
    ))

    registry.register(ToolSpec(
        name="write_file",
        description=(
            "Write content to a file. Creates parent directories "
            "if needed. Overwrites existing content."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to write the file",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file",
                },
            },
            "required": ["path", "content"],
        },
        handler=_write_file,
    ))

    registry.register(ToolSpec(
        name="list_directory",
        description=(
            "List files and directories at the given path. "
            "Shows type (d=directory, f=file) and size."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path to list (default: current directory)",
                    "default": ".",
                },
            },
            "required": [],
        },
        handler=_list_directory,
    ))

    return registry
