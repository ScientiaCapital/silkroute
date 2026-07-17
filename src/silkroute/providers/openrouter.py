"""Direct-vendor and OpenRouter adapters for Mantis agents via langchain-openai.

Uses ChatOpenAI with base_url override — battle-tested, actively maintained.
NOT langchain-openrouter (39 downloads/week, inactive, known bugs).

DeepSeek, Zhipu (GLM), and DashScope (Qwen) each publish an OpenAI-compatible
endpoint, so the same ChatOpenAI(base_url=...) pattern reaches them directly.
OpenRouter is simply one more entry in the provider→base-URL table, letting
``create_openrouter_model`` collapse into a thin wrapper over
``create_direct_model``.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from silkroute.providers.models import Provider

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Each vendor's OpenAI-compatible endpoint. DeepSeek/Zhipu/DashScope all publish
# one, so ChatOpenAI reaches them directly with only the base_url changed.
_PROVIDER_BASE_URLS: dict[Provider, str] = {
    Provider.OPENROUTER: _OPENROUTER_BASE_URL,
    Provider.DEEPSEEK: "https://api.deepseek.com/v1",
    Provider.GLM: "https://open.bigmodel.cn/api/paas/v4",
    Provider.QWEN: "https://dashscope.aliyuncs.com/compatible-mode/v1",
}

# API-key env-var fallback chain per provider (first non-empty wins).
_PROVIDER_ENV_KEYS: dict[Provider, tuple[str, ...]] = {
    Provider.OPENROUTER: ("MANTIS_OPENROUTER_API_KEY", "SILKROUTE_OPENROUTER_API_KEY"),
    Provider.DEEPSEEK: ("SILKROUTE_DEEPSEEK_API_KEY",),
    Provider.GLM: ("SILKROUTE_GLM_API_KEY",),
    Provider.QWEN: ("SILKROUTE_QWEN_API_KEY",),
}

# Human-friendly provider labels for error messages.
_PROVIDER_LABELS: dict[Provider, str] = {
    Provider.OPENROUTER: "OpenRouter",
    Provider.DEEPSEEK: "DeepSeek",
    Provider.GLM: "GLM",
    Provider.QWEN: "Qwen",
}

# OpenRouter-specific attribution headers. Direct vendors don't need them.
_DEFAULT_HEADERS = {
    "HTTP-Referer": "https://github.com/ScientiaCapital/silkroute",
    "X-Title": "SilkRoute Mantis",
}


def create_direct_model(
    provider: Provider,
    model_id: str,
    api_key: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 4096,
    extra_headers: dict[str, str] | None = None,
) -> ChatOpenAI:
    """Create a ChatOpenAI routed to a vendor's own OpenAI-compatible endpoint.

    Args:
        provider: Which vendor to route to (DeepSeek, GLM, Qwen, or OpenRouter).
        model_id: The model name the vendor's endpoint expects. For direct
            vendors this is the *native* name (e.g. "deepseek-v4-flash"), not
            the OpenRouter slug — see ``providers.models.DIRECT_MODEL_NAMES``.
        api_key: Explicit API key. Falls back to the provider's env vars.
        temperature: Sampling temperature. 0.0 for deterministic output.
        max_tokens: Maximum tokens in the response.
        extra_headers: Additional headers (merged with OpenRouter defaults when
            provider is OpenRouter).

    Returns:
        A ChatOpenAI instance configured for the given vendor.

    Raises:
        ValueError: If the provider has no direct endpoint, or no API key found.
    """
    # Imported lazily so this module (and the local Ollama research path that
    # imports it) doesn't require the `mantis` extra just to load. Only the
    # actual cloud/direct-vendor path needs langchain-openai installed.
    from langchain_openai import ChatOpenAI

    base_url = _PROVIDER_BASE_URLS.get(provider)
    if base_url is None:
        raise ValueError(
            f"Provider '{provider}' has no direct OpenAI-compatible endpoint. "
            f"Supported: {', '.join(str(p) for p in _PROVIDER_BASE_URLS)}."
        )

    resolved_key = api_key or _resolve_provider_key(provider)

    headers: dict[str, str] = {}
    if provider == Provider.OPENROUTER:
        headers.update(_DEFAULT_HEADERS)
    if extra_headers:
        headers.update(extra_headers)

    return ChatOpenAI(
        model=model_id,
        base_url=base_url,
        api_key=resolved_key,
        temperature=temperature,
        max_tokens=max_tokens,
        default_headers=headers or None,
    )


def create_openrouter_model(
    model_id: str = "deepseek/deepseek-v3.2",
    api_key: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 4096,
    extra_headers: dict[str, str] | None = None,
) -> ChatOpenAI:
    """Create a ChatOpenAI instance routed through OpenRouter.

    Thin wrapper over :func:`create_direct_model` for the OpenRouter provider,
    preserving the historical default model and header behavior.

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
    return create_direct_model(
        Provider.OPENROUTER,
        model_id=model_id,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        extra_headers=extra_headers,
    )


def _resolve_provider_key(provider: Provider) -> str:
    """Resolve a provider's API key from its env-var fallback chain."""
    for env_var in _PROVIDER_ENV_KEYS.get(provider, ()):
        value = os.environ.get(env_var)
        if value:
            return value
    chain = " or ".join(_PROVIDER_ENV_KEYS.get(provider, ()))
    label = _PROVIDER_LABELS.get(provider, str(provider))
    raise ValueError(
        f"No {label} API key found. Set {chain or 'the provider API key'}."
    )


def _resolve_api_key() -> str:
    """Resolve OpenRouter API key with fallback chain.

    Order: MANTIS_OPENROUTER_API_KEY → SILKROUTE_OPENROUTER_API_KEY
    """
    return _resolve_provider_key(Provider.OPENROUTER)
