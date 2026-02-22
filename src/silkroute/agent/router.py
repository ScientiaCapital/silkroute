"""Model selection with 4-level priority cascade.

Selects the best Chinese LLM for a given task tier and capabilities,
then generates the correct litellm model string for API routing.

When ``SILKROUTE_USE_LITELLM_PROXY=true``, model strings are rewritten
to the ``silkroute-*`` aliases defined in ``litellm_config.yaml``,
routing traffic through the LiteLLM proxy at localhost:4000.
"""

from __future__ import annotations

import os

from silkroute.config.settings import ModelTier, ProviderConfig
from silkroute.providers.models import (
    DEFAULT_ROUTING,
    MODELS_BY_TIER,
    Capability,
    ModelSpec,
    Provider,
    get_model,
)


def select_model(
    tier: ModelTier,
    capabilities: list[Capability] | None = None,
    preferred_model: str | None = None,
) -> ModelSpec:
    """Select the best model using a 4-level priority cascade.

    1. User override (--model flag) → direct lookup
    2. Capability-scored selection from tier models
    3. DEFAULT_ROUTING fallback chain (first available)
    4. Absolute fallback: DeepSeek V3.2
    """
    # Level 1: User override
    if preferred_model:
        model = get_model(preferred_model)
        if model:
            return model

    # Level 2: Capability-scored selection
    if capabilities:
        candidates = MODELS_BY_TIER.get(tier, [])
        # Filter to non-local models with tool calling support
        candidates = [
            m for m in candidates
            if m.provider != Provider.OLLAMA and m.supports_tool_calling
        ]
        if candidates:
            best = max(candidates, key=lambda m: _score_model(m, capabilities))
            return best

    # Level 3: DEFAULT_ROUTING fallback chain
    for model_id in DEFAULT_ROUTING.get(tier, []):
        model = get_model(model_id)
        if model and model.provider != Provider.OLLAMA:
            return model

    # Level 4: Absolute fallback
    fallback = get_model("deepseek/deepseek-v3.2")
    assert fallback is not None, "DeepSeek V3.2 must exist in registry"
    return fallback


def _score_model(model: ModelSpec, required: list[Capability]) -> float:
    """Score a model based on how well it matches required capabilities.

    Each matching capability = 1.0 point.
    AGENTIC capability gets a 0.5 bonus (strongly prefer agentic models for tool-heavy work).
    """
    score = 0.0
    for cap in required:
        if cap in model.capabilities:
            score += 1.0
            if cap == Capability.AGENTIC:
                score += 0.5
    return score


def get_litellm_model_string(model: ModelSpec) -> str:
    """Generate the correct litellm model string for API routing.

    Priority order:
    1. LiteLLM proxy mode → ``silkroute-*`` alias (routes via localhost:4000)
    2. Ollama models → model_id as-is
    3. Direct API key → bare model_id
    4. Otherwise → ``openrouter/`` prefix
    """
    # Proxy mode: use silkroute-* aliases from litellm_config.yaml
    if _use_litellm_proxy():
        alias = _PROXY_MODEL_MAP.get(model.model_id)
        if alias:
            return alias

    if model.provider == Provider.OLLAMA:
        return model.model_id

    if _is_provider_available(model.provider):
        return model.model_id

    # Route through OpenRouter
    return f"openrouter/{model.model_id}"


# Maps model_id → LiteLLM proxy alias name (from litellm_config.yaml).
# A unit test asserts these keys stay in sync with the model registry.
_PROXY_MODEL_MAP: dict[str, str] = {
    "qwen/qwen3-coder:free": "silkroute-free-coder",
    "deepseek/deepseek-r1-0528:free": "silkroute-free-reasoning",
    "z-ai/glm-4.5-air:free": "silkroute-free-general",
    "deepseek/deepseek-v3.2": "silkroute-standard",
    "qwen/qwen3-235b-a22b-2507": "silkroute-standard-fallback",
    "z-ai/glm-4.7": "silkroute-standard-tools",
    "qwen/qwen3-30b-a3b": "silkroute-standard-light",
    "deepseek/deepseek-r1-0528": "silkroute-premium",
    "qwen/qwen3-coder": "silkroute-premium-code",
    "z-ai/glm-5": "silkroute-premium-agent",
    "moonshotai/kimi-k2": "silkroute-premium-multiagent",
}


def _use_litellm_proxy() -> bool:
    """Check if LiteLLM proxy mode is enabled."""
    return ProviderConfig().use_litellm_proxy


_PROVIDER_ENV_KEYS: dict[Provider, str] = {
    Provider.DEEPSEEK: "SILKROUTE_DEEPSEEK_API_KEY",
    Provider.QWEN: "SILKROUTE_QWEN_API_KEY",
    Provider.GLM: "SILKROUTE_GLM_API_KEY",
    Provider.MOONSHOT: "SILKROUTE_MOONSHOT_API_KEY",
}


def _is_provider_available(provider: Provider) -> bool:
    """Check if a direct provider API key is configured."""
    env_key = _PROVIDER_ENV_KEYS.get(provider)
    if not env_key:
        return False
    return bool(os.environ.get(env_key))
