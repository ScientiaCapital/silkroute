"""Shell command sandbox — validates and restricts agent shell execution.

Provides defense-in-depth for LLM-driven shell commands:
1. Command blocklist: rejects destructive/exfiltration patterns
2. Working directory enforcement: confines execution to workspace
3. Resource limits: memory cap + timeout

Prompt injection via malicious repo files can trick the LLM into
executing arbitrary commands, so we validate even "trusted" LLM output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
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


def build_sandbox_env(config: SandboxConfig) -> dict[str, str]:
    """Build environment variables for sandboxed subprocess execution."""
    import os

    env = os.environ.copy()
    # Set working directory hint
    env["SILKROUTE_WORKSPACE"] = str(config.workspace_dir)
    return env
