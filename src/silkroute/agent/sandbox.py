"""Shell command guard for agent shell execution — NOT a security boundary.

What this module does:
1. Command denylist: rejects a list of obviously destructive / exfiltration
   patterns (``rm -rf``, ``curl | sh``, ``sudo``, ...). This is a speed bump
   against accidents and naive prompt injection, not a security boundary: the
   shell is a full programming language, so a determined or injected command
   can trivially rephrase around any regex denylist.
2. Working directory: commands start in the workspace directory (they can
   still ``cd`` or use absolute paths elsewhere).
3. Scrubbed environment (:func:`build_sandbox_env`): child processes get only
   an allowlist of variables (PATH, HOME, LANG, TERM, ...); anything that
   looks like a credential (``*KEY*``, ``*TOKEN*``, ``*SECRET*``,
   ``*PASSWORD*``) and all ``SILKROUTE_*`` / ``OPENROUTER_*`` / ``ANTHROPIC_*``
   variables are dropped, so the agent's own API keys are not visible to it.
4. Memory cap (:func:`make_preexec_fn`): on POSIX, ``RLIMIT_AS`` is set to
   ``max_memory_mb`` in the child. Linux enforces it; macOS largely ignores
   ``RLIMIT_AS``, so treat it as best-effort there.

There is no filesystem, network or process isolation here. Commands run as
the same user, with the same file access and network access as SilkRoute.
Untrusted workloads (or exposing ``shell_exec`` to untrusted MCP clients /
prompts) need a real isolation layer such as a container or VM with no
credentials mounted.
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import structlog

log = structlog.get_logger()

# ============================================================================
# Blocklist patterns — reject before execution
# ============================================================================

# Each tuple: (compiled regex, human-readable reason)
_BLOCKED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Destructive filesystem operations
    (re.compile(r"\brm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?/\s"), "rm targeting root filesystem"),
    (re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s"), "recursive forced delete"),
    (re.compile(r"\brm\s+-[a-zA-Z]*f[a-zA-Z]*r[a-zA-Z]*\s"), "recursive forced delete"),
    (re.compile(r"\bmkfs\b"), "filesystem format"),
    (re.compile(r"\bdd\s+.*of=/dev/"), "raw disk write"),
    # Download-and-execute patterns (common in prompt injection)
    (re.compile(r"curl\s.*\|\s*(sh|bash|zsh|python|perl)"), "download and execute"),
    (re.compile(r"wget\s.*\|\s*(sh|bash|zsh|python|perl)"), "download and execute"),
    (re.compile(r"curl\s.*>\s*/tmp/.*&&.*sh\s"), "download-write-execute"),
    # Dangerous git operations
    (re.compile(r"\bgit\s+push\s+.*--force\b"), "force push"),
    (re.compile(r"\bgit\s+push\s+-f\b"), "force push"),
    (re.compile(r"\bgit\s+reset\s+--hard\b"), "hard reset"),
    (re.compile(r"\bgit\s+clean\s+-[a-zA-Z]*f"), "forced clean"),
    # Process/system manipulation
    (re.compile(r"\bkill\s+-9\s+-1\b"), "kill all processes"),
    (re.compile(r"\bkillall\b"), "kill all by name"),
    (re.compile(r"\bchmod\s+.*777\s+/"), "open permissions on root paths"),
    (re.compile(r"\bchown\s+.*root"), "change ownership to root"),
    # Network exfiltration
    (re.compile(r"\bnc\s+-[a-zA-Z]*l"), "netcat listener"),
    (re.compile(r"\bssh\s.*-R\s"), "reverse SSH tunnel"),
    # Credential theft
    (re.compile(r"cat\s+.*\.ssh/"), "read SSH keys"),
    (re.compile(r"cat\s+.*\.env\b"), "read environment secrets"),
    (re.compile(r"cat\s+.*/etc/(passwd|shadow)"), "read system credentials"),
    # Privilege escalation
    (re.compile(r"\bsudo\b"), "sudo usage"),
    (re.compile(r"\bsu\s+-"), "switch user"),
    (re.compile(r"\bdoas\b"), "doas usage"),
]


@dataclass
class SandboxViolation:
    """Describes why a command was rejected."""

    command: str
    reason: str
    pattern: str


@dataclass
class SandboxConfig:
    """Configuration for the shell sandbox."""

    workspace_dir: Path
    max_memory_mb: int = 512
    blocked_patterns: list[tuple[re.Pattern[str], str]] | None = None
    allow_outside_workspace: bool = False
    # Extra environment variable names passed through to child processes
    # (still subject to the credential-name filter).
    env_allowlist: frozenset[str] = field(default_factory=frozenset)

    @property
    def effective_patterns(self) -> list[tuple[re.Pattern[str], str]]:
        if self.blocked_patterns is not None:
            return self.blocked_patterns
        return _BLOCKED_PATTERNS


def validate_command(command: str, config: SandboxConfig) -> SandboxViolation | None:
    """Check a command against the sandbox rules.

    Returns None if the command is allowed, or a SandboxViolation if blocked.
    """
    # Normalize: collapse whitespace for pattern matching
    normalized = " ".join(command.split())

    # Check blocklist patterns
    for pattern, reason in config.effective_patterns:
        if pattern.search(normalized):
            log.warning(
                "sandbox_blocked",
                command=command[:200],
                reason=reason,
            )
            return SandboxViolation(
                command=command[:200],
                reason=reason,
                pattern=pattern.pattern,
            )

    # Working directory enforcement
    if not config.allow_outside_workspace:
        violation = _check_path_traversal(normalized, config.workspace_dir)
        if violation is not None:
            return violation

    return None


def _check_path_traversal(command: str, workspace: Path) -> SandboxViolation | None:
    """Detect path traversal attempts that escape the workspace.

    Checks for explicit .. sequences and absolute paths to sensitive dirs.
    We only block clearly dangerous paths — agents legitimately need to
    read system files like /usr/include for compilation tasks.
    """
    workspace_str = str(workspace.resolve())

    # Sensitive directories that should never be targets of write operations
    _write_commands = ("rm", "mv", "cp", "chmod", "chown", "write_file", "tee", ">", ">>")
    sensitive_dirs = ("/etc/", "/var/", "/usr/", "/sys/", "/proc/", "/dev/")

    # Check if any write command targets sensitive directories
    for write_cmd in _write_commands:
        if write_cmd in command:
            for sensitive in sensitive_dirs:
                if sensitive in command:
                    return SandboxViolation(
                        command=command[:200],
                        reason=f"write operation targeting {sensitive}",
                        pattern=f"{write_cmd}.*{sensitive}",
                    )

    # Detect traversal out of workspace via cd or explicit paths
    # Only flag if the command tries to operate on parent directories
    _cd_traversal = re.search(r"\bcd\s+.*\.\./\.\.", command)
    if _cd_traversal:
        log.warning("sandbox_path_traversal", command=command[:200], workspace=workspace_str)
        return SandboxViolation(
            command=command[:200],
            reason="directory traversal (cd with multiple ..)",
            pattern=r"cd\s+.*\.\./\.\.",
        )

    return None


# Variables passed through to child processes by default.
_ENV_ALLOWLIST: frozenset[str] = frozenset(
    {
        "PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TERM",
        "USER",
        "LOGNAME",
        "SHELL",
        "TMPDIR",
        "TZ",
    }
)

# Never passed through, even if allowlisted.
_ENV_DENY_SUBSTRINGS: tuple[str, ...] = ("KEY", "TOKEN", "SECRET", "PASSWORD")
_ENV_DENY_PREFIXES: tuple[str, ...] = ("SILKROUTE_", "OPENROUTER_", "ANTHROPIC_")


def _env_name_denied(name: str) -> bool:
    upper = name.upper()
    return upper.startswith(_ENV_DENY_PREFIXES) or any(s in upper for s in _ENV_DENY_SUBSTRINGS)


def build_sandbox_env(
    config: SandboxConfig | None = None,
    source: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build a scrubbed environment for agent child processes.

    Only allowlisted names are kept (``_ENV_ALLOWLIST`` plus
    ``config.env_allowlist``), and any name that looks like a credential or
    belongs to SilkRoute / OpenRouter / Anthropic is dropped regardless.
    """
    env_source = os.environ if source is None else source
    allowed = _ENV_ALLOWLIST | (config.env_allowlist if config is not None else frozenset())
    return {
        name: value
        for name, value in env_source.items()
        if name in allowed and not _env_name_denied(name)
    }


def make_preexec_fn(max_memory_mb: int | None) -> Callable[[], None] | None:
    """Return a ``preexec_fn`` that caps the child's address space (POSIX only).

    Returns None on Windows or when no cap is configured. Failures to set the
    limit (e.g. on platforms that reject RLIMIT_AS) are ignored so the child
    still starts.
    """
    if not max_memory_mb or max_memory_mb <= 0 or sys.platform == "win32":
        return None

    limit = int(max_memory_mb) * 1024 * 1024

    def _apply_limits() -> None:
        import resource

        try:
            _soft, hard = resource.getrlimit(resource.RLIMIT_AS)
            new_hard = limit if hard == resource.RLIM_INFINITY else min(limit, hard)
            resource.setrlimit(resource.RLIMIT_AS, (min(limit, new_hard), new_hard))
        except (ValueError, OSError):
            pass

    return _apply_limits
