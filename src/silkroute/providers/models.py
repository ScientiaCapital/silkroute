"""Model registry — Chinese-LLM-optimized, model-agnostic.

Defines all supported models with pricing, capabilities, context windows,
tool-calling support, and routing tier assignments. This is the knowledge base
that powers SilkRoute's intelligent cost routing.

Default posture is local-first / Chinese for sovereignty and cost, but the
architecture is provider-neutral: western frontier models (Claude/GPT/Gemini)
plug in as a one-line ``ModelSpec`` each and route through OpenRouter with no
router changes (see the WESTERN FRONTIER section below).

Pricing data as of February 2026. Updated monthly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from silkroute.config.settings import ModelTier


class Provider(StrEnum):
    """LLM providers. Chinese + local are the default posture; western frontier
    providers (Anthropic/OpenAI/Google) are supported via the OpenRouter fallback
    transport and require no router changes."""

    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    GLM = "z-ai"
    MOONSHOT = "moonshotai"
    OPENROUTER = "openrouter"
    OLLAMA = "ollama"
    # Western frontier — routed via OpenRouter (not in router._DIRECT_PROVIDER_PREFIX)
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"


class Capability(StrEnum):
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

    # Local-hardware metadata (Ollama models only; 0.0 = not applicable/cloud model).
    # Approximate total unified memory needed to run comfortably (weights + context
    # + OS overhead), not just the raw Q4 download size. Used to pick models that
    # actually fit a given machine — e.g. an 8GB M1 vs. a 24GB M4.
    min_ram_gb: float = 0.0

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
# WESTERN FRONTIER MODELS (via OpenRouter — model-agnostic proof)
# ============================================================================
# These are NOT the default posture — local/Chinese stay first in every routing
# chain for sovereignty and cost. They exist to prove the architecture is truly
# provider-neutral: each is a one-line ModelSpec with provider=ANTHROPIC/OPENAI/
# GOOGLE (absent from router._DIRECT_PROVIDER_PREFIX), so get_litellm_model_string
# routes them as "openrouter/{model_id}" with NO router changes. Frontier is
# opt-in per deployment (needs SILKROUTE_OPENROUTER_API_KEY). Slugs + pricing +
# context verified 2026-07-17 against https://openrouter.ai/api/v1/models.

CLAUDE_SONNET_5 = ModelSpec(
    model_id="anthropic/claude-sonnet-5",
    name="Claude Sonnet 5",
    provider=Provider.ANTHROPIC,
    tier=ModelTier.PREMIUM,
    input_cost_per_m=2.00,
    output_cost_per_m=10.00,
    context_window=1_000_000,
    max_output_tokens=128_000,
    capabilities=(
        Capability.CODING,
        Capability.REASONING,
        Capability.TOOL_CALLING,
        Capability.AGENTIC,
        Capability.LONG_CONTEXT,
        Capability.MULTIMODAL,
    ),
    recommended_for=("frontier_coding", "complex_agentic_workflows", "architecture_decisions"),
)

GPT_5_6_SOL = ModelSpec(
    model_id="openai/gpt-5.6-sol",
    name="GPT-5.6 Sol",
    provider=Provider.OPENAI,
    tier=ModelTier.PREMIUM,
    input_cost_per_m=5.00,
    output_cost_per_m=30.00,
    context_window=1_050_000,
    max_output_tokens=128_000,
    capabilities=(
        Capability.CODING,
        Capability.REASONING,
        Capability.TOOL_CALLING,
        Capability.AGENTIC,
        Capability.LONG_CONTEXT,
        Capability.MULTIMODAL,
        Capability.MATH,
    ),
    recommended_for=("frontier_reasoning", "hardest_debugging", "research"),
)

GEMINI_3_5_FLASH = ModelSpec(
    model_id="google/gemini-3.5-flash",
    name="Gemini 3.5 Flash",
    provider=Provider.GOOGLE,
    tier=ModelTier.STANDARD,
    input_cost_per_m=1.50,
    output_cost_per_m=9.00,
    context_window=1_048_576,
    max_output_tokens=65_536,
    capabilities=(
        Capability.CODING,
        Capability.REASONING,
        Capability.TOOL_CALLING,
        Capability.LONG_CONTEXT,
        Capability.MULTIMODAL,
    ),
    recommended_for=("long_context_analysis", "multimodal_tasks", "fast_general_purpose"),
)

GPT_5_6_LUNA = ModelSpec(
    model_id="openai/gpt-5.6-luna",
    name="GPT-5.6 Luna",
    provider=Provider.OPENAI,
    tier=ModelTier.STANDARD,
    input_cost_per_m=1.00,
    output_cost_per_m=6.00,
    context_window=1_050_000,
    max_output_tokens=128_000,
    capabilities=(
        Capability.CODING,
        Capability.TOOL_CALLING,
        Capability.AGENTIC,
        Capability.LONG_CONTEXT,
    ),
    recommended_for=("cost_efficient_frontier", "daily_agent_ops", "tool_heavy_tasks"),
)

# Smallest western model — fast + cheap + strong tool-calling. The latency-first
# cloud brain for live-event AV control (a Pi delegates fast commands here). Lands
# in STANDARD (not FREE — FREE stays $0/local-first) because default AV commands
# classify STANDARD; Sonnet 5 (PREMIUM) is the reasoning step-up. Uses budget_tokens
# thinking, not adaptive — fine for tool-calling. Routes openrouter/{model_id}.
CLAUDE_HAIKU_4_5 = ModelSpec(
    model_id="anthropic/claude-haiku-4-5",
    name="Claude Haiku 4.5",
    provider=Provider.ANTHROPIC,
    tier=ModelTier.STANDARD,
    input_cost_per_m=1.00,
    output_cost_per_m=5.00,
    context_window=200_000,
    max_output_tokens=64_000,
    capabilities=(
        Capability.CODING,
        Capability.TOOL_CALLING,
        Capability.AGENTIC,
    ),
    recommended_for=("live_event_control", "low_latency_tool_calling", "fast_device_control"),
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
    min_ram_gb=24.0,  # MoE stores all experts in RAM even though only 3B are active/token
)

GLM_4_9B_LOCAL = ModelSpec(
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
    min_ram_gb=8.0,  # ~5.5-6GB Q4 weights; the only pre-existing local model that fits an 8GB M1
)

QWEN2_5_7B_LOCAL = ModelSpec(
    model_id="ollama/qwen2.5:7b",
    name="Qwen2.5 7B (Local)",
    provider=Provider.OLLAMA,
    tier=ModelTier.FREE,
    input_cost_per_m=0.0,
    output_cost_per_m=0.0,
    context_window=32_768,
    max_output_tokens=8_192,
    capabilities=(Capability.TOOL_CALLING, Capability.AGENTIC),
    total_params_b=7.0,
    active_params_b=7.0,
    is_moe=False,
    is_free=True,
    recommended_for=("local_lightweight", "offline_device_control", "privacy_sensitive"),
    min_ram_gb=8.0,  # Verified 2026-07-12 via ollama.com/library/qwen2.5 — 4.7GB Q4 download
)

QWEN2_5_14B_LOCAL = ModelSpec(
    model_id="ollama/qwen2.5:14b",
    name="Qwen2.5 14B (Local)",
    provider=Provider.OLLAMA,
    tier=ModelTier.FREE,
    input_cost_per_m=0.0,
    output_cost_per_m=0.0,
    context_window=32_768,
    max_output_tokens=8_192,
    capabilities=(Capability.TOOL_CALLING, Capability.AGENTIC),
    total_params_b=14.0,
    active_params_b=14.0,
    is_moe=False,
    is_free=True,
    recommended_for=("local_agentic_tools", "offline_device_control", "privacy_sensitive"),
    min_ram_gb=16.0,  # Does NOT fit an 8GB M1 — needs the 24GB M4 or bigger
)

QWEN2_5_32B_LOCAL = ModelSpec(
    model_id="ollama/qwen2.5:32b",
    name="Qwen2.5 32B (Local)",
    provider=Provider.OLLAMA,
    tier=ModelTier.FREE,
    input_cost_per_m=0.0,
    output_cost_per_m=0.0,
    context_window=32_768,
    max_output_tokens=8_192,
    capabilities=(Capability.TOOL_CALLING, Capability.AGENTIC),
    total_params_b=32.0,
    active_params_b=32.0,
    is_moe=False,
    is_free=True,
    recommended_for=("local_agentic_tools", "offline_device_control", "privacy_sensitive"),
    min_ram_gb=24.0,  # Does NOT fit an 8GB M1 — needs the 24GB M4 or bigger
)

# Verified 2026-07-12 against https://ollama.com/library/deepseek-r1 — real tag,
# "DeepSeek-R1-Distill-Qwen-14B", 9.0GB, 128K context (context_window below is
# left at the repo's existing conservative default).
DEEPSEEK_R1_14B_LOCAL = ModelSpec(
    model_id="ollama/deepseek-r1:14b",
    name="DeepSeek R1 14B (Local)",
    provider=Provider.OLLAMA,
    tier=ModelTier.FREE,
    input_cost_per_m=0.0,
    output_cost_per_m=0.0,
    context_window=32_768,
    max_output_tokens=8_192,
    capabilities=(Capability.REASONING, Capability.TOOL_CALLING),
    total_params_b=14.0,
    active_params_b=14.0,
    is_moe=False,
    is_free=True,
    recommended_for=("local_agentic_tools", "offline_device_control", "privacy_sensitive"),
    min_ram_gb=16.0,  # 9GB Q4 file alone exceeds an 8GB M1's total unified memory
)

# GLM_CURRENT_LOCAL ("ollama/glm4.6:9b") removed 2026-07-12 — verified against
# ollama.com and independent sources that GLM-4.6 is a ~355B-parameter MoE model
# (32B active) with no 9B variant; no such tag exists, and none of Zhipu's other
# current-gen releases (GLM-4.5-Air, 106B/12B active) come close to a genuinely
# lightweight 9B footprint either. GLM_4_9B_LOCAL (glm4:9b) remains the only
# local GLM option until a real small current-gen tag exists.

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
    # Western frontier (via OpenRouter — opt-in, model-agnostic proof)
    CLAUDE_SONNET_5.model_id: CLAUDE_SONNET_5,
    CLAUDE_HAIKU_4_5.model_id: CLAUDE_HAIKU_4_5,
    GPT_5_6_SOL.model_id: GPT_5_6_SOL,
    GEMINI_3_5_FLASH.model_id: GEMINI_3_5_FLASH,
    GPT_5_6_LUNA.model_id: GPT_5_6_LUNA,
    # Local
    QWEN3_30B_LOCAL.model_id: QWEN3_30B_LOCAL,
    GLM_4_9B_LOCAL.model_id: GLM_4_9B_LOCAL,
    QWEN2_5_7B_LOCAL.model_id: QWEN2_5_7B_LOCAL,
    QWEN2_5_14B_LOCAL.model_id: QWEN2_5_14B_LOCAL,
    QWEN2_5_32B_LOCAL.model_id: QWEN2_5_32B_LOCAL,
    DEEPSEEK_R1_14B_LOCAL.model_id: DEEPSEEK_R1_14B_LOCAL,
}

MODELS_BY_TIER: dict[ModelTier, list[ModelSpec]] = {
    ModelTier.FREE: [
        QWEN3_CODER_FREE,
        DEEPSEEK_R1_FREE,
        GLM_45_AIR_FREE,
        QWEN3_30B_LOCAL,
        GLM_4_9B_LOCAL,
        QWEN2_5_7B_LOCAL,
        QWEN2_5_14B_LOCAL,
        QWEN2_5_32B_LOCAL,
        DEEPSEEK_R1_14B_LOCAL,
    ],
    ModelTier.STANDARD: [
        DEEPSEEK_V3_2,
        QWEN3_235B,
        QWEN3_30B,
        GLM_47,
        # Western frontier (opt-in; listed after Chinese to keep local-first posture)
        CLAUDE_HAIKU_4_5,
        GEMINI_3_5_FLASH,
        GPT_5_6_LUNA,
    ],
    ModelTier.PREMIUM: [
        DEEPSEEK_R1,
        QWEN3_CODER,
        GLM_5,
        KIMI_K2,
        # Western frontier (opt-in; listed after Chinese to keep local-first posture)
        CLAUDE_SONNET_5,
        GPT_5_6_SOL,
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
        # Western frontier last — opt-in fallback, keeps Chinese/local first
        "anthropic/claude-haiku-4-5",
        "google/gemini-3.5-flash",
        "openai/gpt-5.6-luna",
    ],
    ModelTier.PREMIUM: [
        "deepseek/deepseek-r1-0528",
        "qwen/qwen3-coder",
        "z-ai/glm-5",
        "moonshotai/kimi-k2",
        # Western frontier last — opt-in fallback, keeps Chinese/local first
        "anthropic/claude-sonnet-5",
        "openai/gpt-5.6-sol",
    ],
}


# ============================================================================
# DIRECT-VENDOR MODEL NAME TRANSLATION
# ============================================================================
# Maps the registry's OpenRouter-style ``model_id`` to each vendor's *native*
# model name, used when a direct provider API key is configured and the router
# routes through litellm's native vendor transport (deepseek/, dashscope/, zai/)
# instead of OpenRouter. The native APIs use different model names than the
# OpenRouter slugs (e.g. OpenRouter "deepseek/deepseek-v3.2" is "deepseek-v4-flash"
# on api.deepseek.com).
#
# Verified 2026-07-12 against vendor docs/announcements. Qwen (DashScope) and
# GLM (Zhipu/bigmodel.cn) names below are confirmed live model names. DeepSeek
# names were updated to the new deepseek-v4-* naming: the legacy "deepseek-chat"
# / "deepseek-reasoner" names are being fully retired 2026-07-24 15:59 UTC — see
# https://api-docs.deepseek.com/news/news260424/. During the migration window
# they alias to deepseek-v4-flash's non-thinking/thinking modes respectively,
# which meant "deepseek/deepseek-r1-0528" (a PREMIUM-tier reasoning model) was
# silently downgraded to Flash-tier reasoning via the "deepseek-reasoner" alias
# instead of the true Pro-tier successor — fixed below by pointing it straight
# at "deepseek-v4-pro". Models absent from this map (e.g. Moonshot/Kimi) have no
# native transport and stay on OpenRouter.
DIRECT_MODEL_NAMES: dict[str, str] = {
    # DeepSeek (api.deepseek.com) — litellm "deepseek/" provider
    "deepseek/deepseek-v3.2": "deepseek-v4-flash",
    "deepseek/deepseek-r1-0528": "deepseek-v4-pro",
    "deepseek/deepseek-r1-0528:free": "deepseek-v4-flash",
    # Qwen (dashscope.aliyuncs.com) — litellm "dashscope/" provider
    "qwen/qwen3-235b-a22b-2507": "qwen-plus",
    "qwen/qwen3-30b-a3b": "qwen-turbo",
    "qwen/qwen3-coder": "qwen3-coder-plus",
    "qwen/qwen3-coder:free": "qwen3-coder-plus",
    # GLM (open.bigmodel.cn / Zhipu) — litellm "zai/" provider
    "z-ai/glm-4.7": "glm-4.7",
    "z-ai/glm-5": "glm-5",
    "z-ai/glm-4.5-air:free": "glm-4.5-air",
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
