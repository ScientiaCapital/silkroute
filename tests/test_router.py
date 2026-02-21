"""Tests for silkroute.agent.router."""

import os
from unittest.mock import patch

from silkroute.agent.router import get_litellm_model_string, select_model
from silkroute.config.settings import ModelTier
from silkroute.providers.models import Capability, Provider


class TestSelectModel:
    def test_user_override(self):
        model = select_model(ModelTier.FREE, preferred_model="deepseek/deepseek-v3.2")
        assert model.model_id == "deepseek/deepseek-v3.2"

    def test_invalid_override_falls_through(self):
        model = select_model(ModelTier.STANDARD, preferred_model="nonexistent/model")
        assert model is not None  # Should still return something via fallback

    def test_capability_scoring_prefers_agentic(self):
        model = select_model(ModelTier.STANDARD, capabilities=[Capability.AGENTIC, Capability.CODING])
        # DeepSeek V3.2 and GLM-4.7 both have AGENTIC; either is valid
        assert Capability.AGENTIC in model.capabilities

    def test_free_tier_returns_non_local(self):
        model = select_model(ModelTier.FREE, capabilities=[Capability.CODING])
        assert model.provider != Provider.OLLAMA

    def test_standard_tier_default(self):
        model = select_model(ModelTier.STANDARD)
        assert model.tier == ModelTier.STANDARD

    def test_premium_tier_default(self):
        model = select_model(ModelTier.PREMIUM)
        assert model.tier == ModelTier.PREMIUM

    def test_absolute_fallback(self):
        # Even with empty capabilities and no matches, should return DeepSeek V3.2
        model = select_model(ModelTier.STANDARD, capabilities=[])
        assert model is not None


class TestGetLitellmModelString:
    def test_ollama_model_passthrough(self):
        from silkroute.providers.models import QWEN3_30B_LOCAL
        result = get_litellm_model_string(QWEN3_30B_LOCAL)
        assert result == "ollama/qwen3:30b-a3b"

    def test_openrouter_prefix_when_no_direct_key(self):
        from silkroute.providers.models import DEEPSEEK_V3_2
        with patch.dict(os.environ, {}, clear=True):
            result = get_litellm_model_string(DEEPSEEK_V3_2)
            assert result.startswith("openrouter/")

    def test_bare_id_with_direct_key(self):
        from silkroute.providers.models import DEEPSEEK_V3_2
        with patch.dict(os.environ, {"SILKROUTE_DEEPSEEK_API_KEY": "sk-test-123"}):
            result = get_litellm_model_string(DEEPSEEK_V3_2)
            assert result == "deepseek/deepseek-v3.2"
            assert not result.startswith("openrouter/")
