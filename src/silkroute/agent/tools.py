"""Tool registry and built-in tools for the ReAct agent.

Provides a registry for tool specifications and 8 built-in tools:
shell_exec, read_file, write_file, list_directory, http_request,
search_grep, git_ops, env_info.

shell_exec runs with a scrubbed environment and, when a workspace is
configured, a command denylist, the workspace as cwd and a memory cap. The
denylist is a speed bump, not a security boundary — see agent.sandbox.

read_file, write_file and list_directory are confined to the workspace root
(the configured workspace, else the current directory): paths are resolved
with symlinks followed and anything outside the root is refused.

http_request is SSRF-guarded (see silkroute.network.ssrf): only public
addresses, fail-closed DNS, redirects followed manually with a check per hop,
and the connection pinned to the checked IP. search_grep is confined to the
workspace when one is configured. git_ops allows only read-only operations
with validated arguments. env_info filters sensitive environment variables.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import platform
import re
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from silkroute.agent.sandbox import (
    SandboxConfig,
    build_sandbox_env,
    make_preexec_fn,
    validate_command,
)
from silkroute.network.ssrf import (
    SSRFBlockedError,
    SSRFPinnedTransport,
    guarded_request,
)
from silkroute.network.ssrf import is_ssrf_blocked as _is_ssrf_blocked

log = structlog.get_logger()

# Module-level sandbox config — set by create_default_registry().
# Threading model: this global is set once per process during registry
# creation and read (but never mutated) during tool execution.
# Safe for concurrent asyncio tasks within a single event loop.
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

    The child always gets a scrubbed environment (no API keys / tokens).
    With a workspace configured it also gets:
    - Denylist check (rejects some destructive/exfiltration patterns)
    - Working directory set to the workspace
    - Address-space cap (RLIMIT_AS = max_memory_mb, POSIX)

    NOTE: This uses create_subprocess_shell intentionally — the agent
    requires shell features (pipes, globbing, env vars). The denylist is a
    speed bump, NOT a security boundary; see agent.sandbox.
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

        # Child never sees SilkRoute's credentials (scrubbed env, always).
        kwargs["env"] = build_sandbox_env(_sandbox_config)

        # Set working directory + memory cap if sandbox is configured
        if _sandbox_config is not None:
            kwargs["cwd"] = str(_sandbox_config.workspace_dir)
            preexec = make_preexec_fn(_sandbox_config.max_memory_mb)
            if preexec is not None:
                kwargs["preexec_fn"] = preexec

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


def _workspace_root() -> Path:
    """Root that file tools are confined to: the sandbox workspace, else CWD."""
    if _sandbox_config is not None:
        return _sandbox_config.workspace_dir.resolve()
    return Path.cwd().resolve()


def _confine_path(path: str) -> Path:
    """Resolve ``path`` inside the workspace root or raise ``PermissionError``.

    Relative paths are resolved against the workspace root. ``Path.resolve()``
    follows symlinks and collapses ``..``, so traversal and symlinks pointing
    outside the root are refused. (A symlink swapped in after this check is a
    TOCTOU race this does not defend against.)
    """
    root = _workspace_root()
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if resolved != root and not resolved.is_relative_to(root):
        raise PermissionError(f"Path '{path}' resolves outside the workspace root {root}")
    return resolved


async def _read_file(path: str, start_line: int = 0, end_line: int = 0) -> str:
    """Read file contents, optionally a specific line range."""
    try:
        p = _confine_path(path)
    except PermissionError as e:
        return f"Error: {e}"
    try:
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
        p = _confine_path(path)
    except PermissionError as e:
        return f"Error: {e}"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} bytes to {p}"
    except Exception as e:
        return f"Error writing file: {e}"


async def _list_directory(path: str = ".") -> str:
    """List files and directories at the given path."""
    try:
        p = _confine_path(path)
    except PermissionError as e:
        return f"Error: {e}"
    try:
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


# ============================================================================
# SSRF protection helpers
# ============================================================================

# Sensitive env var patterns — keys matching these will be redacted
_SENSITIVE_ENV_PATTERNS = re.compile(r"(KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL)", re.IGNORECASE)

# Allowed git read-only operations
_GIT_ALLOWED_OPS: frozenset[str] = frozenset(
    {"status", "diff", "log", "show", "blame", "branch", "remote", "tag"}
)

# Arguments refused for every git operation: writing files (--output/-o),
# reading files outside the repo (--no-index), running configured external
# programs (--ext-diff, --textconv), and option injection via --exec style flags.
_GIT_FORBIDDEN_ARGS: tuple[str, ...] = (
    "--output",
    "-o",
    "--no-index",
    "--ext-diff",
    "--textconv",
    "--exec",
    "--upload-pack",
    "--receive-pack",
)

# branch / tag: listing only. Positional args (which would create a ref) are
# allowed only together with --list / -l, where they are match patterns.
_GIT_LIST_FLAGS: dict[str, frozenset[str]] = {
    "branch": frozenset(
        {
            "-a",
            "--all",
            "-r",
            "--remotes",
            "-v",
            "-vv",
            "--verbose",
            "--list",
            "-l",
            "--show-current",
            "--no-color",
            "--color",
            "--no-abbrev",
            "-i",
            "--ignore-case",
            "--merged",
            "--no-merged",
        }
    ),
    "tag": frozenset(
        {"-l", "--list", "-n", "--no-color", "--color", "-i", "--ignore-case", "--merged"}
    ),
}
_GIT_LIST_VALUE_PREFIXES: tuple[str, ...] = (
    "--sort=",
    "--format=",
    "--contains=",
    "--no-contains=",
    "--merged=",
    "--no-merged=",
    "--points-at=",
    "--column=",
    "-n",
)


def _validate_git_args(operation: str, argv: list[str]) -> str | None:
    """Return a refusal reason if ``git <operation> <argv>`` is not read-only."""
    for arg in argv:
        lowered = arg.lower()
        name = lowered.split("=", 1)[0]
        for bad in _GIT_FORBIDDEN_ARGS:
            if name == bad:
                return f"argument '{arg}' is not allowed"
            # git accepts unambiguous abbreviations of long options
            # (e.g. --outp=FILE means --output=FILE).
            if bad.startswith("--") and len(name) > 2 and bad.startswith(name):
                return f"argument '{arg}' is not allowed"
        # Short-flag clusters like "-po" or "-ofile" that include -o.
        if lowered.startswith("-o") and not lowered.startswith("--"):
            return f"argument '{arg}' is not allowed"

    if operation in _GIT_LIST_FLAGS:
        allowed = _GIT_LIST_FLAGS[operation]
        list_mode = any(a in ("--list", "-l") for a in argv)
        for arg in argv:
            if arg.startswith("-"):
                if arg not in allowed and not arg.startswith(_GIT_LIST_VALUE_PREFIXES):
                    return f"'{operation} {arg}' is not allowed (listing only)"
            elif not list_mode:
                return (
                    f"'{operation} {arg}' would create or modify a ref; "
                    f"use --list for patterns (listing only)"
                )
    elif operation == "remote":
        if argv and argv not in (["-v"], ["--verbose"]) and argv[0] != "get-url":
            return f"'remote {' '.join(argv)}' is not allowed (only listing / get-url)"
        if argv and argv[0] == "get-url" and any(a.startswith("-") for a in argv[1:]):
            return "'remote get-url' flags are not allowed"
    return None


# Skip directories that are never useful to grep
_SKIP_DIRS: frozenset[str] = frozenset({".git", "__pycache__", "node_modules"})


async def _http_request(
    url: str,
    method: str = "GET",
    headers: str = "",
    body: str = "",
    timeout: int = 10,
) -> str:
    """Make an HTTP request with SSRF protection.

    Blocks RFC 1918, loopback, link-local addresses, and file:// scheme.
    Response body is truncated at 20KB. Timeout is clamped to 1-60s.
    """
    import httpx

    # Clamp timeout
    timeout = min(max(timeout, 1), 60)

    # SSRF check
    block_reason = _is_ssrf_blocked(url)
    if block_reason is not None:
        return f"Error: SSRF protection blocked request — {block_reason}"

    # Parse headers JSON
    parsed_headers: dict[str, str] = {}
    if headers.strip():
        try:
            raw = json.loads(headers)
            if isinstance(raw, dict):
                parsed_headers = {str(k): str(v) for k, v in raw.items()}
        except json.JSONDecodeError as exc:
            return f"Error: Invalid headers JSON — {exc}"

    method = method.upper()
    content: bytes | None = body.encode() if body else None

    try:
        # Redirects are followed manually so every hop is SSRF-checked, and the
        # pinned transport connects only to the address it just validated
        # (defeats DNS rebinding between check and connect).
        async with httpx.AsyncClient(
            follow_redirects=False, transport=SSRFPinnedTransport()
        ) as client:
            response = await guarded_request(
                client,
                method,
                url,
                headers=parsed_headers,
                content=content,
                timeout=timeout,
            )

        # Limit body to 20KB
        raw_body = response.text
        truncated = False
        max_bytes = 20 * 1024
        if len(response.content) > max_bytes:
            # Decode up to max_bytes
            raw_body = response.content[:max_bytes].decode(errors="replace")
            truncated = True

        resp_headers = "\n".join(f"  {k}: {v}" for k, v in response.headers.items())
        result = f"Status: {response.status_code}\nHeaders:\n{resp_headers}\nBody:\n{raw_body}"
        if truncated:
            result += f"\n... (truncated at 20KB, full size: {len(response.content):,} bytes)"
        return result

    except SSRFBlockedError as exc:
        return f"Error: SSRF protection blocked request — {exc}"
    except httpx.TimeoutException:
        return f"Error: Request timed out after {timeout}s"
    except httpx.RequestError as exc:
        return f"Error: Request failed — {exc}"


async def _search_grep(
    pattern: str,
    path: str = ".",
    glob_filter: str = "",
    max_results: int = 50,
    context_lines: int = 2,
) -> str:
    """Search file contents using regex pattern.

    Skips binary files, .git/, __pycache__/, node_modules/ directories.
    Respects workspace_dir sandbox config when set.
    """
    # Resolve search root — honor workspace sandbox
    if _sandbox_config is not None:
        try:
            root = _confine_path(path)
        except PermissionError as exc:
            return f"Error: {exc}"
    else:
        root = Path(path).expanduser().resolve()

    if not root.exists():
        return f"Error: Path not found: {path}"
    if not root.is_dir():
        return f"Error: Not a directory: {path}"

    try:
        compiled = re.compile(pattern, re.MULTILINE)
    except re.error as exc:
        return f"Error: Invalid regex pattern — {exc}"

    # Collect candidate files
    candidate_files = list(root.rglob(glob_filter)) if glob_filter else list(root.rglob("*"))

    # Filter to files only, skip blacklisted dirs
    def _in_skip_dir(p: Path) -> bool:
        return any(part in _SKIP_DIRS for part in p.parts)

    # Skip symlinks that resolve outside the search root (no reading through
    # a link to files elsewhere on disk).
    files = [
        f
        for f in candidate_files
        if f.is_file() and not _in_skip_dir(f) and f.resolve().is_relative_to(root)
    ]

    results: list[str] = []
    total_matches = 0

    for file_path in sorted(files):
        if total_matches >= max_results:
            break
        try:
            text = file_path.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, OSError):
            # Skip binary or unreadable files
            continue

        lines = text.splitlines()
        for lineno, line in enumerate(lines, start=1):
            if total_matches >= max_results:
                break
            if compiled.search(line):
                # Gather context
                start = max(0, lineno - 1 - context_lines)
                end = min(len(lines), lineno + context_lines)
                ctx_block: list[str] = []
                for ctx_lineno in range(start, end):
                    marker = ">" if ctx_lineno == lineno - 1 else " "
                    ctx_block.append(f"{marker} {file_path}:{ctx_lineno + 1}: {lines[ctx_lineno]}")
                results.append("\n".join(ctx_block))
                total_matches += 1

    if not results:
        return f"No matches found for pattern '{pattern}' in {root}"

    output = "\n---\n".join(results)
    if total_matches >= max_results:
        output += f"\n\n... (results capped at {max_results})"
    return output


async def _git_ops(operation: str, args: str = "") -> str:
    """Run a read-only git operation.

    Only status, diff, log, show, blame, branch, remote and tag are allowed,
    and their arguments are validated by :func:`_validate_git_args`:
    no --output/-o, --no-index, --ext-diff/--textconv; branch/tag may only
    list; remote may only list (-v) or get-url. push, reset, config, etc. are
    not in the operation allowlist at all.
    """
    operation = operation.lower().strip()

    if operation not in _GIT_ALLOWED_OPS:
        return (
            f"Error: Operation '{operation}' is not allowed. "
            f"Allowed: {', '.join(sorted(_GIT_ALLOWED_OPS))}"
        )

    argv = args.split()
    refusal = _validate_git_args(operation, argv)
    if refusal is not None:
        return f"Error: git {operation} refused — {refusal}"

    # Build git command arguments using exec (no shell expansion)
    cmd_parts = ["git", operation, *argv]

    cwd: str | None = None
    if _sandbox_config is not None:
        cwd = str(_sandbox_config.workspace_dir)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        output = stdout.decode(errors="replace")
        err = stderr.decode(errors="replace")

        if proc.returncode != 0:
            if err:
                return f"Error (exit {proc.returncode}):\n{err}"
            return f"Error: git exited with code {proc.returncode}"

        if not output.strip() and err.strip():
            output = err  # Some git ops write to stderr (e.g., diff --stat)

        if len(output) > 10_000:
            output = output[:10_000] + f"\n... (truncated, {len(output)} chars total)"
        return output or "(no output)"
    except TimeoutError:
        return "Error: git operation timed out after 30s"
    except FileNotFoundError:
        return "Error: git executable not found"
    except Exception as exc:
        return f"Error: {exc}"


async def _env_info(query: str = "all") -> str:
    """Get environment information.

    Sensitive env vars (matching KEY, SECRET, TOKEN, PASSWORD, CREDENTIAL)
    are filtered out. Query options: python, os, packages, cwd, all.
    """
    query = query.lower().strip()
    sections: list[str] = []

    if query in {"python", "all"}:
        venv = os.environ.get("VIRTUAL_ENV", "(not set)")
        paths = "\n    ".join(sys.path)
        sections.append(
            f"Python:\n"
            f"  version: {sys.version}\n"
            f"  executable: {sys.executable}\n"
            f"  virtual_env: {venv}\n"
            f"  sys.path:\n    {paths}"
        )

    if query in {"os", "all"}:
        # Filter sensitive env vars
        safe_env = {k: v for k, v in os.environ.items() if not _SENSITIVE_ENV_PATTERNS.search(k)}
        env_lines = "\n    ".join(f"{k}={v}" for k, v in sorted(safe_env.items()))
        sections.append(
            f"OS:\n"
            f"  platform: {platform.system()} {platform.release()}\n"
            f"  machine: {platform.machine()}\n"
            f"  hostname: {platform.node()}\n"
            f"  env vars (filtered):\n    {env_lines}"
        )

    if query in {"packages", "all"}:
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "pip",
                "list",
                "--format=columns",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
            pkg_output = stdout.decode(errors="replace")
            if len(pkg_output) > 5_000:
                pkg_output = pkg_output[:5_000] + "\n... (truncated)"
            sections.append(f"Packages:\n{pkg_output}")
        except Exception as exc:
            sections.append(f"Packages:\n  Error fetching packages: {exc}")

    if query in {"cwd", "all"}:
        sections.append(f"CWD:\n  {Path.cwd()}")

    if not sections:
        return f"Error: Unknown query '{query}'. Options: python, os, packages, cwd, all"

    return "\n\n".join(sections)


def create_default_registry(
    workspace_dir: str | None = None,
    skill_registry: Any | None = None,  # noqa: ANN401
    skill_ctx: Any | None = None,  # noqa: ANN401
) -> ToolRegistry:
    """Create a registry with the 8 built-in tools.

    If workspace_dir is provided, shell_exec commands are sandboxed:
    blocklist validation, working directory enforcement, and resource limits.

    Args:
        workspace_dir: Optional path to restrict shell and grep operations.
        skill_registry: Optional skill registry to mount into the tool registry.
        skill_ctx: Optional context for skill execution (required if skill_registry set).
    """
    global _sandbox_config  # noqa: PLW0603

    if workspace_dir is not None:
        _sandbox_config = SandboxConfig(workspace_dir=Path(workspace_dir).resolve())
    else:
        _sandbox_config = None

    registry = ToolRegistry()

    registry.register(
        ToolSpec(
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
        )
    )

    registry.register(
        ToolSpec(
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
        )
    )

    registry.register(
        ToolSpec(
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
        )
    )

    registry.register(
        ToolSpec(
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
        )
    )

    registry.register(
        ToolSpec(
            name="http_request",
            description=(
                "Make an HTTP request to a URL. Supports GET, POST, PUT, DELETE, PATCH, HEAD."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to request"},
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"],
                        "default": "GET",
                    },
                    "headers": {
                        "type": "string",
                        "description": "JSON string of headers",
                        "default": "",
                    },
                    "body": {
                        "type": "string",
                        "description": "Request body (for POST/PUT/PATCH)",
                        "default": "",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (1-60)",
                        "default": 10,
                    },
                },
                "required": ["url"],
            },
            handler=_http_request,
        )
    )

    registry.register(
        ToolSpec(
            name="search_grep",
            description=(
                "Search file contents using regex pattern. "
                "Returns matching lines with file paths and line numbers."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex pattern to search for"},
                    "path": {
                        "type": "string",
                        "description": "Directory to search in",
                        "default": ".",
                    },
                    "glob_filter": {
                        "type": "string",
                        "description": "File glob pattern (e.g. '*.py')",
                        "default": "",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum results to return",
                        "default": 50,
                    },
                    "context_lines": {
                        "type": "integer",
                        "description": "Lines of context around matches",
                        "default": 2,
                    },
                },
                "required": ["pattern"],
            },
            handler=_search_grep,
        )
    )

    registry.register(
        ToolSpec(
            name="git_ops",
            description=(
                "Run read-only git operations. "
                "Supports: status, diff, log, show, blame, branch, remote, tag."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": [
                            "status",
                            "diff",
                            "log",
                            "show",
                            "blame",
                            "branch",
                            "remote",
                            "tag",
                        ],
                    },
                    "args": {
                        "type": "string",
                        "description": "Additional arguments for the git command",
                        "default": "",
                    },
                },
                "required": ["operation"],
            },
            handler=_git_ops,
        )
    )

    registry.register(
        ToolSpec(
            name="env_info",
            description="Get environment information. Query: python, os, packages, cwd, all.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "enum": ["python", "os", "packages", "cwd", "all"],
                        "default": "all",
                    },
                },
                "required": [],
            },
            handler=_env_info,
        )
    )

    # Bridge skills to tool registry if provided
    if skill_registry is not None and skill_ctx is not None:
        skill_registry.mount(registry, skill_ctx)

    return registry
