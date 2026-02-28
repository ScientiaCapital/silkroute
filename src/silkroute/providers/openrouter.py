"""OpenRouter adapter for Mantis agents via langchain-openai.

Uses ChatOpenAI with base_url override — battle-tested, actively maintained.
NOT langchain-openrouter (39 downloads/week, inactive, known bugs).
"""

from __future__ import annotations

import os

from langchain_openai import ChatOpenAI

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

_DEFAULT_HEADERS = {
    "HTTP-Referer": "https://github.com/ScientiaCapital/silkroute",
    "X-Title": "SilkRoute Mantis",
}


def create_openrouter_model(
    model_id: str = "deepseek/deepseek-v3.2",
    api_key: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 4096,
    extra_headers: dict[str, str] | None = None,
) -> ChatOpenAI:
    """Create a ChatOpenAI instance routed through OpenRouter.

    Args:
        model_id: OpenRouter model identifier (e.g. "deepseek/deepseek-v3.2").
        api_key: Explicit API key. Falls back to env vars if not provided.
        temperature: Sampling temperature. 0.0 for deterministic output.
        max_tokens: Maximum tokens in the response.
        extra_headers: Additional headers merged with defaults.

    Returns:
        A ChatOpenAI instance configured for OpenRouter.

    Raises:
        ValueError: If no API key is found.
    """
    resolved_key = api_key or _resolve_api_key()

    headers = {**_DEFAULT_HEADERS}
    if extra_headers:
        headers.update(extra_headers)

    return ChatOpenAI(
        model=model_id,
        base_url=_OPENROUTER_BASE_URL,
        api_key=resolved_key,
        temperature=temperature,
        max_tokens=max_tokens,
        default_headers=headers,
    )


def _resolve_api_key() -> str:
    """Resolve OpenRouter API key with fallback chain.

    Order: MANTIS_OPENROUTER_API_KEY → SILKROUTE_OPENROUTER_API_KEY
    """
    key = os.environ.get("MANTIS_OPENROUTER_API_KEY") or os.environ.get(
        "SILKROUTE_OPENROUTER_API_KEY"
    )
    if not key:
        raise ValueError(
            "No OpenRouter API key found. "
            "Set MANTIS_OPENROUTER_API_KEY or SILKROUTE_OPENROUTER_API_KEY."
        )
    return key
