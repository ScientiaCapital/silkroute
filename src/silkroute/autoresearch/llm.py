"""LLM interaction — propose code changes via Chinese LLMs through OpenRouter."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from silkroute.providers.openrouter import create_openrouter_model

logger = logging.getLogger(__name__)

_SYSTEM_TEMPLATE = """\
{program}

## Output Format

You MUST respond with valid JSON only. No markdown, no explanation, no code fences.
The JSON must have exactly these fields:

{{
  "file_path": "relative path to the file to modify",
  "old_code": "exact code to replace (must match the file exactly)",
  "new_code": "replacement code",
  "rationale": "one-line description of what this change does and why"
}}

Rules:
- Propose exactly ONE change per response.
- The old_code must be an exact substring of the current file contents.
- The new_code must be different from old_code.
- Keep changes under {max_lines} lines of diff.
- Only modify files within: {allowed_paths}
"""

_USER_TEMPLATE = """\
## Current State

{context}

## Files You Can Modify

{file_listing}

Propose your next experiment. Respond with JSON only.
"""


@dataclass
class ProposedChange:
    """A code change proposed by the LLM researcher."""

    file_path: str
    old_code: str
    new_code: str
    rationale: str


async def propose_change(
    model_id: str,
    program: str,
    context: str,
    target_files: list[Path],
    allowed_paths: list[str],
    max_diff_lines: int,
) -> ProposedChange:
    """Ask a Chinese LLM to propose one code change.

    Args:
        model_id: OpenRouter model identifier.
        program: Contents of the program.md file.
        context: Current state (test output, coverage, recent history).
        target_files: Files the agent can see and edit.
        allowed_paths: Path prefixes the agent is allowed to modify.
        max_diff_lines: Maximum lines of diff per experiment.

    Returns:
        A ProposedChange with file path, old/new code, and rationale.

    Raises:
        ValueError: If the LLM response can't be parsed as valid JSON.
    """
    llm = create_openrouter_model(
        model_id=model_id,
        temperature=0.7,  # Creative exploration, not deterministic
        max_tokens=4096,
    )

    system_msg = _SYSTEM_TEMPLATE.format(
        program=program,
        max_lines=max_diff_lines,
        allowed_paths=", ".join(allowed_paths),
    )

    file_listing = _build_file_listing(target_files)
    user_msg = _USER_TEMPLATE.format(context=context, file_listing=file_listing)

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]

    response = await llm.ainvoke(messages)
    content = response.content
    if not isinstance(content, str):
        content = str(content)

    return _parse_response(content)


def _build_file_listing(files: list[Path], max_lines_per_file: int = 200) -> str:
    """Build a file listing with contents for the LLM to review."""
    parts: list[str] = []
    for fp in files:
        if not fp.exists():
            continue
        content = fp.read_text()
        lines = content.splitlines()
        if len(lines) > max_lines_per_file:
            truncated = "\n".join(lines[:max_lines_per_file])
            parts.append(
                f"### {fp}\n```\n{truncated}\n"
                f"... (truncated at {max_lines_per_file} lines)\n```"
            )
        else:
            parts.append(f"### {fp}\n```\n{content}\n```")
    return "\n\n".join(parts) if parts else "(no files found)"


def _parse_response(content: str) -> ProposedChange:
    """Parse LLM response into a ProposedChange.

    Handles both raw JSON and JSON wrapped in markdown code fences.
    """
    text = content.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove first line (```json or ```) and last line (```)
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM response is not valid JSON: {e}\nResponse: {text[:500]}") from e

    required = {"file_path", "old_code", "new_code", "rationale"}
    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"LLM response missing required fields: {missing}")

    if data["old_code"] == data["new_code"]:
        raise ValueError("LLM proposed no-op change (old_code == new_code)")

    return ProposedChange(
        file_path=data["file_path"],
        old_code=data["old_code"],
        new_code=data["new_code"],
        rationale=data["rationale"],
    )
