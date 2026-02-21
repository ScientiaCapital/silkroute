"""Chinese LLM model registry.

Defines all supported Chinese models with pricing, capabilities, context windows,
tool-calling support, and routing tier assignments. This is the knowledge base
that powers SilkRoute's intelligent cost routing.

Pricing data as of February 2026. Updated monthly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from silkroute.config.settings import ModelTier


class Provider(str, Enum):
    """Chinese LLM providers."""

    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    GLM = "z-ai"
    MOONSHOT = "moonshotai"
    OPENROUTER = "openrouter"
    OLLAMA = "ollama"


class Capability(str, Enum):
    """Model capability flags for routing decisions."""

    CODING = "coding"
    REASONING = "reasoning"
    TOOL_CALLING = "tool_calling"
    LONG_CONTEXT = "long_context"
    MULTIMODAL = "multimodal"
    AGENTIC = "agentic"
    MATH = "math"
    CREATIVE = "creative"


@dataclass(frozen=True)
class ModelSpec:
    """Complete specification for a Chinese LLM."""

    # Identity
    model_id: str  # OpenRouter-format ID (e.g., "deepseek/deepseek-v3.2")
    name: str  # Human-readable name
    provider: Provider
    tier: ModelTier

    # Pricing (USD per million tokens)
    input_cost_per_m: float
    output_cost_per_m: float

    # Capabilities
    context_window: int  # Max tokens
    max_output_tokens: int
    capabilities: tuple[Capability, ...] = field(default_factory=tuple)
    supports_tool_calling: bool = True
    supports_streaming: bool = True

    # Architecture info
    total_params_b: float = 0.0  # Total parameters (billions)
    active_params_b: float = 0.0  # Active params per inference (MoE)
    is_moe: bool = False

    # Routing metadata
    is_free: bool = False
    rate_limit_rpm: int = 0  # 0 = no known limit
    recommended_for: tuple[str, ...] = field(default_factory=tuple)

    @property
    def cost_per_1k_input(self) -> float:
        """Cost per 1,000 input tokens."""
        return self.input_cost_per_m / 1000

    @property
    def cost_per_1k_output(self) -> float:
        """Cost per 1,000 output tokens."""
        return self.output_cost_per_m / 1000


# ============================================================================
# TIER 1: FREE MODELS
# Rate-limited but zero cost — maximize usage for simple tasks
# ============================================================================

QWEN3_CODER_FREE = ModelSpec(
    model_id="qwen/qwen3-coder:free",
    name="Qwen3 Coder (Free)",
    provider=Provider.QWEN,
    tier=ModelTier.FREE,
    input_cost_per_m=0.0,
    output_cost_per_m=0.0,
    context_window=262_144,
    max_output_tokens=65_536,
    capabilities=(Capability.CODING, Capability.TOOL_CALLING, Capability.LONG_CONTEXT),
    total_params_b=480.0,
    active_params_b=35.0,
    is_moe=True,
    is_free=True,
    rate_limit_rpm=20,
    recommended_for=("simple_code_review", "docstring_generation", "test_writing"),
)

DEEPSEEK_R1_FREE = ModelSpec(
    model_id="deepseek/deepseek-r1-0528:free",
    name="DeepSeek R1 (Free)",
    provider=Provider.DEEPSEEK,
    tier=ModelTier.FREE,
    input_cost_per_m=0.0,
    output_cost_per_m=0.0,
    context_window=128_000,
    max_output_tokens=64_000,
    capabilities=(Capability.REASONING, Capability.MATH, Capability.CODING),
    total_params_b=685.0,
    active_params_b=37.0,
    is_moe=True,
    is_free=True,
    rate_limit_rpm=20,
    recommended_for=("simple_reasoning", "issue_triage", "commit_message_generation"),
)

GLM_45_AIR_FREE = ModelSpec(
    model_id="z-ai/glm-4.5-air:free",
    name="GLM-4.5 Air (Free)",
    provider=Provider.GLM,
    tier=ModelTier.FREE,
    input_cost_per_m=0.0,
    output_cost_per_m=0.0,
    context_window=128_000,
    max_output_tokens=4_096,
    capabilities=(Capability.TOOL_CALLING, Capability.CREATIVE),
    is_free=True,
    rate_limit_rpm=20,
    recommended_for=("summarization", "template_responses", "status_checks"),
)

# ============================================================================
# TIER 2: STANDARD MODELS
# Cost-effective workhorses for daily agent operations
# ============================================================================

DEEPSEEK_V3_2 = ModelSpec(
    model_id="deepseek/deepseek-v3.2",
    name="DeepSeek V3.2",
    provider=Provider.DEEPSEEK,
    tier=ModelTier.STANDARD,
    input_cost_per_m=0.25,
    output_cost_per_m=0.38,
    context_window=128_000,
    max_output_tokens=64_000,
    capabilities=(
        Capability.CODING,
        Capability.REASONING,
        Capability.TOOL_CALLING,
        Capability.AGENTIC,
    ),
    total_params_b=685.0,
    active_params_b=37.0,
    is_moe=True,
    recommended_for=("code_review", "pr_description", "bug_analysis", "refactoring"),
)

QWEN3_235B = ModelSpec(
    model_id="qwen/qwen3-235b-a22b-2507",
    name="Qwen3 235B",
    provider=Provider.QWEN,
    tier=ModelTier.STANDARD,
    input_cost_per_m=0.07,
    output_cost_per_m=0.46,
    context_window=131_072,
    max_output_tokens=8_192,
    capabilities=(
        Capability.CODING,
        Capability.REASONING,
        Capability.TOOL_CALLING,
        Capability.LONG_CONTEXT,
    ),
    total_params_b=235.0,
    active_params_b=22.0,
    is_moe=True,
    recommended_for=("code_review", "documentation", "general_analysis"),
)

QWEN3_30B = ModelSpec(
    model_id="qwen/qwen3-30b-a3b",
    name="Qwen3 30B-A3B",
    provider=Provider.QWEN,
    tier=ModelTier.STANDARD,
    input_cost_per_m=0.06,
    output_cost_per_m=0.22,
    context_window=131_072,
    max_output_tokens=8_192,
    capabilities=(Capability.CODING, Capability.TOOL_CALLING),
    total_params_b=30.0,
    active_params_b=3.0,
    is_moe=True,
    recommended_for=("lightweight_tasks", "formatting", "simple_edits"),
)

GLM_47 = ModelSpec(
    model_id="z-ai/glm-4.7",
    name="GLM-4.7",
    provider=Provider.GLM,
    tier=ModelTier.STANDARD,
    input_cost_per_m=0.25,
    output_cost_per_m=1.00,
    context_window=128_000,
    max_output_tokens=16_384,
    capabilities=(
        Capability.CODING,
        Capability.TOOL_CALLING,
        Capability.AGENTIC,
    ),
    recommended_for=("tool_heavy_tasks", "multi_step_workflows", "ci_debugging"),
)

# ============================================================================
# TIER 3: PREMIUM MODELS
# Maximum capability for complex reasoning and heavy coding
# ============================================================================

DEEPSEEK_R1 = ModelSpec(
    model_id="deepseek/deepseek-r1-0528",
    name="DeepSeek R1",
    provider=Provider.DEEPSEEK,
    tier=ModelTier.PREMIUM,
    input_cost_per_m=0.40,
    output_cost_per_m=1.75,
    context_window=128_000,
    max_output_tokens=64_000,
    capabilities=(
        Capability.REASONING,
        Capability.MATH,
        Capability.CODING,
        Capability.AGENTIC,
    ),
    total_params_b=685.0,
    active_params_b=37.0,
    is_moe=True,
    recommended_for=("complex_debugging", "architecture_decisions", "security_review"),
)

QWEN3_CODER = ModelSpec(
    model_id="qwen/qwen3-coder",
    name="Qwen3 Coder 480B",
    provider=Provider.QWEN,
    tier=ModelTier.PREMIUM,
    input_cost_per_m=0.22,
    output_cost_per_m=0.95,
    context_window=262_144,
    max_output_tokens=65_536,
    capabilities=(
        Capability.CODING,
        Capability.TOOL_CALLING,
        Capability.LONG_CONTEXT,
        Capability.AGENTIC,
    ),
    total_params_b=480.0,
    active_params_b=35.0,
    is_moe=True,
    recommended_for=("heavy_refactoring", "new_feature_implementation", "codebase_migration"),
)

GLM_5 = ModelSpec(
    model_id="z-ai/glm-5",
    name="GLM-5",
    provider=Provider.GLM,
    tier=ModelTier.PREMIUM,
    input_cost_per_m=1.00,
    output_cost_per_m=3.20,
    context_window=128_000,
    max_output_tokens=16_384,
    capabilities=(
        Capability.CODING,
        Capability.REASONING,
        Capability.TOOL_CALLING,
        Capability.AGENTIC,
        Capability.CREATIVE,
    ),
    total_params_b=745.0,
    active_params_b=44.0,
    is_moe=True,
    recommended_for=("agentic_workflows", "creative_content", "complex_tool_chains"),
)

KIMI_K2 = ModelSpec(
    model_id="moonshotai/kimi-k2",
    name="Kimi K2",
    provider=Provider.MOONSHOT,
    tier=ModelTier.PREMIUM,
    input_cost_per_m=0.39,
    output_cost_per_m=1.90,
    context_window=131_072,
    max_output_tokens=16_384,
    capabilities=(
        Capability.CODING,
        Capability.REASONING,
        Capability.TOOL_CALLING,
        Capability.AGENTIC,
    ),
    total_params_b=1000.0,
    active_params_b=32.0,
    is_moe=True,
    recommended_for=("multi_step_agents", "long_horizon_tasks", "research"),
)

# ============================================================================
# LOCAL MODELS (Ollama — zero API cost)
# ============================================================================

QWEN3_30B_LOCAL = ModelSpec(
    model_id="ollama/qwen3:30b-a3b",
    name="Qwen3 30B (Local)",
    provider=Provider.OLLAMA,
    tier=ModelTier.FREE,
    input_cost_per_m=0.0,
    output_cost_per_m=0.0,
    context_window=131_072,
    max_output_tokens=8_192,
    capabilities=(Capability.CODING, Capability.TOOL_CALLING),
    total_params_b=30.0,
    active_params_b=3.0,
    is_moe=True,
    is_free=True,
    recommended_for=("local_simple_tasks", "offline_coding", "privacy_sensitive"),
)

GLM_47_9B_LOCAL = ModelSpec(
    model_id="ollama/glm4:9b",
    name="GLM-4 9B (Local)",
    provider=Provider.OLLAMA,
    tier=ModelTier.FREE,
    input_cost_per_m=0.0,
    output_cost_per_m=0.0,
    context_window=128_000,
    max_output_tokens=4_096,
    capabilities=(Capability.TOOL_CALLING, Capability.CREATIVE),
    total_params_b=9.0,
    active_params_b=9.0,
    is_moe=False,
    is_free=True,
    recommended_for=("local_lightweight", "summaries", "drafts"),
)

# ============================================================================
# MODEL REGISTRY
# ============================================================================

ALL_MODELS: dict[str, ModelSpec] = {
    # Free tier
    QWEN3_CODER_FREE.model_id: QWEN3_CODER_FREE,
    DEEPSEEK_R1_FREE.model_id: DEEPSEEK_R1_FREE,
    GLM_45_AIR_FREE.model_id: GLM_45_AIR_FREE,
    # Standard tier
    DEEPSEEK_V3_2.model_id: DEEPSEEK_V3_2,
    QWEN3_235B.model_id: QWEN3_235B,
    QWEN3_30B.model_id: QWEN3_30B,
    GLM_47.model_id: GLM_47,
    # Premium tier
    DEEPSEEK_R1.model_id: DEEPSEEK_R1,
    QWEN3_CODER.model_id: QWEN3_CODER,
    GLM_5.model_id: GLM_5,
    KIMI_K2.model_id: KIMI_K2,
    # Local
    QWEN3_30B_LOCAL.model_id: QWEN3_30B_LOCAL,
    GLM_47_9B_LOCAL.model_id: GLM_47_9B_LOCAL,
}

MODELS_BY_TIER: dict[ModelTier, list[ModelSpec]] = {
    ModelTier.FREE: [
        QWEN3_CODER_FREE,
        DEEPSEEK_R1_FREE,
        GLM_45_AIR_FREE,
        QWEN3_30B_LOCAL,
        GLM_47_9B_LOCAL,
    ],
    ModelTier.STANDARD: [
        DEEPSEEK_V3_2,
        QWEN3_235B,
        QWEN3_30B,
        GLM_47,
    ],
    ModelTier.PREMIUM: [
        DEEPSEEK_R1,
        QWEN3_CODER,
        GLM_5,
        KIMI_K2,
    ],
}

# Default routing preferences (first available wins)
DEFAULT_ROUTING: dict[ModelTier, list[str]] = {
    ModelTier.FREE: [
        "qwen/qwen3-coder:free",
        "deepseek/deepseek-r1-0528:free",
        "z-ai/glm-4.5-air:free",
        "ollama/qwen3:30b-a3b",
        "ollama/glm4:9b",
    ],
    ModelTier.STANDARD: [
        "deepseek/deepseek-v3.2",
        "qwen/qwen3-235b-a22b-2507",
        "z-ai/glm-4.7",
        "qwen/qwen3-30b-a3b",
    ],
    ModelTier.PREMIUM: [
        "deepseek/deepseek-r1-0528",
        "qwen/qwen3-coder",
        "z-ai/glm-5",
        "moonshotai/kimi-k2",
    ],
}


def get_model(model_id: str) -> ModelSpec | None:
    """Get model specification by ID."""
    return ALL_MODELS.get(model_id)


def get_cheapest_model(tier: ModelTier, capability: Capability | None = None) -> ModelSpec | None:
    """Get the cheapest model in a tier, optionally filtered by capability."""
    candidates = MODELS_BY_TIER.get(tier, [])
    if capability:
        candidates = [m for m in candidates if capability in m.capabilities]
    if not candidates:
        return None
    return min(candidates, key=lambda m: m.input_cost_per_m + m.output_cost_per_m)


def estimate_cost(
    model: ModelSpec,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Estimate cost in USD for a given token count."""
    input_cost = (input_tokens / 1_000_000) * model.input_cost_per_m
    output_cost = (output_tokens / 1_000_000) * model.output_cost_per_m
    return input_cost + output_cost
