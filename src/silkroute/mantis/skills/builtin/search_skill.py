"""Search/grep skill using pathlib + re (no external dependencies).

Provides regex-based file search across the workspace, respecting
workspace_dir from SkillContext.
"""

from __future__ import annotations

import re
from pathlib import Path

import structlog

from silkroute.mantis.skills.models import SkillCategory, SkillContext, SkillSpec

log = structlog.get_logger()

_DEFAULT_MAX_RESULTS = 50
_DEFAULT_CONTEXT_LINES = 2


async def _search_grep_handler(
    pattern: str,
    path: str = ".",
    glob_filter: str = "**/*",
    max_results: int = _DEFAULT_MAX_RESULTS,
    context_lines: int = _DEFAULT_CONTEXT_LINES,
    _skill_ctx: SkillContext | None = None,
) -> str:
    """Search for a regex pattern across files in the workspace."""
    max_results = min(max(max_results, 1), 500)
    context_lines = min(max(context_lines, 0), 10)

    # Determine root directory
    workspace = Path(_skill_ctx.workspace_dir if _skill_ctx else ".").resolve()
    search_root = (workspace / path).resolve()

    # Security: stay within workspace
    try:
        search_root.relative_to(workspace)
    except ValueError:
        return f"Error: path '{path}' is outside the workspace"

    if not search_root.exists():
        return f"Error: path '{search_root}' does not exist"

    try:
        compiled = re.compile(pattern)
    except re.error as e:
        return f"Error: invalid regex pattern '{pattern}': {e}"

    results: list[str] = []
    matches_found = 0

    # Collect files
    if search_root.is_file():
        files = [search_root]
    else:
        try:
            files = [f for f in search_root.glob(glob_filter) if f.is_file()]
        except Exception as e:
            return f"Error: glob '{glob_filter}' failed: {e}"

    for file_path in sorted(files):
        if matches_found >= max_results:
            break

        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        lines = text.splitlines()

        for line_num, line in enumerate(lines, start=1):
            if matches_found >= max_results:
                break
            if not compiled.search(line):
                continue

            # Build context
            start = max(0, line_num - 1 - context_lines)
            end = min(len(lines), line_num + context_lines)
            context_block = []

            for ctx_idx in range(start, end):
                ctx_line_num = ctx_idx + 1
                marker = ">" if ctx_line_num == line_num else " "
                context_block.append(f"{marker} {ctx_line_num}: {lines[ctx_idx]}")

            try:
                rel_path = file_path.relative_to(workspace)
            except ValueError:
                rel_path = file_path

            match_header = f"\n{rel_path}:{line_num}"
            results.append(match_header + "\n" + "\n".join(context_block))
            matches_found += 1

    if not results:
        return f"No matches found for pattern '{pattern}'"

    header = f"Found {matches_found} match(es) for '{pattern}':"
    if matches_found >= max_results:
        header += f" (capped at {max_results})"

    return header + "".join(results)


search_grep_skill = SkillSpec(
    name="search_grep",
    description=(
        "Search for a regex pattern across files in the workspace. "
        "Returns file:line formatted results with context lines."
    ),
    category=SkillCategory.SEARCH,
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regular expression pattern to search for",
            },
            "path": {
                "type": "string",
                "description": (
                    "Directory or file path to search (relative to workspace, default: '.')"
                ),
                "default": ".",
            },
            "glob_filter": {
                "type": "string",
                "description": "Glob pattern to filter files (default: '**/*')",
                "default": "**/*",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of matches to return (default: 50)",
                "default": 50,
            },
            "context_lines": {
                "type": "integer",
                "description": "Lines of context to show around each match (default: 2)",
                "default": 2,
            },
        },
        "required": ["pattern"],
    },
    handler=_search_grep_handler,
    required_tools=[],
)
