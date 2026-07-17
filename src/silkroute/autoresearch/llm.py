"""LLM interaction — propose code changes via Chinese LLMs.

The researcher runs through OpenRouter by default, or fully local via Ollama
when the model id starts with "ollama/" (e.g. "ollama/qwen2.5:14b") — a $0,
zero-cloud research loop, matching how agent/loop.py reaches local models.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from silkroute.providers.openrouter import create_openrouter_model

logger = logging.getLogger(__name__)

# Local models get a much smaller file listing (see propose_change): a few
# files, each short enough to show complete so the model never guesses at
# truncated code.
_LOCAL_MAX_FILES = 4
_LOCAL_MAX_LINES = 150


def _line_count(fp: Path) -> int:
    """Line count of a file, or a large sentinel if unreadable (so it's skipped)."""
    try:
        return len(fp.read_text().splitlines())
    except OSError:
        return 10**9

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
- old_code MUST be copied verbatim from a file shown below. Prefer the SMALLEST
  unique snippet — often a single line. Do NOT guess or reconstruct code you
  cannot see in full; only reference code that appears in the listing.
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
        model_id: Model identifier. An OpenRouter slug (e.g. "deepseek/deepseek-v3.2"),
            or "ollama/<model>" for fully-local inference (no cloud, no API key).
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
    is_local = model_id.startswith("ollama/")

    system_msg = _SYSTEM_TEMPLATE.format(
        program=program,
        max_lines=max_diff_lines,
        allowed_paths=", ".join(allowed_paths),
    )

    # Local models (e.g. a 14B) lose output-schema discipline when the prompt
    # gets large — at ~70KB they abandon the requested JSON shape. They also
    # hallucinate old_code for any file shown truncated ("...assume the rest").
    # So a local researcher gets a few SMALL files shown COMPLETE (never
    # truncated); cloud models handle the full listing fine.
    if is_local:
        small = [f for f in target_files if _line_count(f) <= _LOCAL_MAX_LINES]
        file_listing = _build_file_listing(
            small[:_LOCAL_MAX_FILES], max_lines_per_file=_LOCAL_MAX_LINES,
        )
    else:
        file_listing = _build_file_listing(target_files)
    user_msg = _USER_TEMPLATE.format(context=context, file_listing=file_listing)

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]

    if is_local:
        content = await _invoke_ollama(model_id, messages)
    else:
        llm = create_openrouter_model(
            model_id=model_id,
            temperature=0.7,  # Creative exploration, not deterministic
            max_tokens=4096,
        )
        response = await llm.ainvoke(messages)
        content = response.content
        if not isinstance(content, str):
            content = str(content)

    return _parse_response(content)


async def _invoke_ollama(model_id: str, messages: list[dict]) -> str:
    """Call a local Ollama model via litellm. No API key, no cloud.

    Mirrors agent/loop.py's litellm usage; api_base honors SILKROUTE_OLLAMA_BASE_URL.
    """
    import litellm

    from silkroute.config.settings import ProviderConfig

    litellm.suppress_debug_info = True
    response = await litellm.acompletion(
        model=model_id,
        messages=messages,
        api_base=ProviderConfig().ollama_base_url,
        temperature=0.7,
        max_tokens=4096,
        response_format={"type": "json_object"},  # litellm maps to Ollama format:json
    )
    return response.choices[0].message.content or ""


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
        # Local models often prepend prose ("Here is the JSON: {...}"). Retry on
        # the outermost {...} span before giving up.
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                data = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                raise ValueError(
                    f"LLM response is not valid JSON: {e}\nResponse: {text[:500]}"
                ) from e
        else:
            raise ValueError(
                f"LLM response is not valid JSON: {e}\nResponse: {text[:500]}"
            ) from e

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
