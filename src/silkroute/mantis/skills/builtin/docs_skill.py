"""Documentation lookup skill backed by Context7.

Wraps Context7Client.query() to provide agents with a simple interface
for fetching library documentation snippets.
"""

from __future__ import annotations

import asyncio

import structlog

from silkroute.mantis.skills.context7 import Context7Client
from silkroute.mantis.skills.models import SkillCategory, SkillContext, SkillSpec

log = structlog.get_logger()

# Module-level client (shared, lazy-initialized)
_default_client: Context7Client | None = None


def _get_default_client() -> Context7Client:
    global _default_client  # noqa: PLW0603
    if _default_client is None:
        _default_client = Context7Client()
    return _default_client


async def _docs_lookup_handler(
    library_name: str,
    query: str,
    _skill_ctx: SkillContext | None = None,
) -> str:
    """Fetch documentation snippets for a library using Context7."""
    client = _get_default_client()

    try:
        result = await client.query(library_name, query)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log.warning("docs_lookup_error", library=library_name, error=str(e), exc_info=True)
        return (
            f"Documentation lookup for '{library_name}' is currently unavailable. "
            f"Error: {e}. Please check official docs manually."
        )

    if result.library is None:
        return (
            f"Could not find library '{library_name}' in Context7. "
            "Try a different name or check the official documentation."
        )

    if not result.snippets:
        return (
            f"Found library '{result.library.name}' (v{result.library.version}) "
            f"but no documentation snippets matched query: '{query}'"
        )

    lines = [
        f"Documentation for '{result.library.name}' v{result.library.version}",
        f"(trust_score: {result.library.trust_score:.2f})",
        f"Query: {query}",
        "",
    ]

    for i, snippet in enumerate(result.snippets, start=1):
        lines.append(f"--- Snippet {i}: {snippet.title} ---")
        if snippet.url:
            lines.append(f"Source: {snippet.url}")
        lines.append(snippet.content)
        lines.append("")

    if result.truncated:
        lines.append("[Results truncated to fit context budget]")

    return "\n".join(lines)


docs_lookup_skill = SkillSpec(
    name="docs_lookup",
    description=(
        "Look up documentation for a library or framework using Context7. "
        "Returns relevant code snippets and explanations. "
        "Fail-open: returns a helpful message if the service is unavailable."
    ),
    category=SkillCategory.DOCS,
    parameters={
        "type": "object",
        "properties": {
            "library_name": {
                "type": "string",
                "description": (
                    "Name of the library or framework (e.g. 'fastapi', 'react', 'numpy')"
                ),
            },
            "query": {
                "type": "string",
                "description": "What to look up in the documentation",
            },
        },
        "required": ["library_name", "query"],
    },
    handler=_docs_lookup_handler,
    required_tools=[],
)
