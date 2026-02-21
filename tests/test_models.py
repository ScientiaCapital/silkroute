"""Tests for silkroute.providers.models."""
import pytest
from silkroute.config.settings import ModelTier
from silkroute.providers.models import (
    ALL_MODELS, MODELS_BY_TIER, get_model, get_cheapest_model, estimate_cost,
    Capability, Provider,
)

class TestModelRegistry:
    def test_total_model_count(self):
        assert len(ALL_MODELS) == 13

    def test_tier_distribution(self):
        assert len(MODELS_BY_TIER[ModelTier.FREE]) == 5  # 3 API + 2 local
        assert len(MODELS_BY_TIER[ModelTier.STANDARD]) == 4
        assert len(MODELS_BY_TIER[ModelTier.PREMIUM]) == 4

    def test_free_models_are_free(self):
        for model in MODELS_BY_TIER[ModelTier.FREE]:
            assert model.is_free is True
            assert model.input_cost_per_m == 0.0

class TestGetModel:
    def test_get_existing_model(self):
        model = get_model("deepseek/deepseek-v3.2")
        assert model is not None
        assert model.name == "DeepSeek V3.2"
        assert model.tier == ModelTier.STANDARD

    def test_get_nonexistent_model(self):
        assert get_model("nonexistent/model") is None

class TestCostEstimation:
    def test_free_model_zero_cost(self):
        model = get_model("qwen/qwen3-coder:free")
        cost = estimate_cost(model, input_tokens=1_000_000, output_tokens=500_000)
        assert cost == 0.0

    def test_standard_model_cost(self):
        model = get_model("deepseek/deepseek-v3.2")
        cost = estimate_cost(model, input_tokens=1_000_000, output_tokens=1_000_000)
        expected = 0.25 + 0.38  # $0.25/M input + $0.38/M output
        assert abs(cost - expected) < 0.001

class TestGetCheapest:
    def test_cheapest_standard(self):
        cheapest = get_cheapest_model(ModelTier.STANDARD)
        assert cheapest is not None
        # Qwen3 30B at $0.06+$0.22 = $0.28 is cheapest standard
        assert cheapest.model_id == "qwen/qwen3-30b-a3b"

    def test_cheapest_with_capability(self):
        cheapest = get_cheapest_model(ModelTier.PREMIUM, Capability.AGENTIC)
        assert cheapest is not None
        assert Capability.AGENTIC in cheapest.capabilities
