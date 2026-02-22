"""Tests for silkroute.agent.router."""

import os
from unittest.mock import patch

from silkroute.agent.router import _PROXY_MODEL_MAP, get_litellm_model_string, select_model
from silkroute.config.settings import ModelTier
from silkroute.providers.models import ALL_MODELS, Capability, Provider


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

    def test_proxy_mode_returns_alias(self):
        from silkroute.providers.models import DEEPSEEK_V3_2
        with patch("silkroute.agent.router._use_litellm_proxy", return_value=True):
            result = get_litellm_model_string(DEEPSEEK_V3_2)
            assert result == "silkroute-standard"

    def test_proxy_mode_fallback_for_unknown_model(self):
        from silkroute.providers.models import QWEN3_30B_LOCAL
        with patch("silkroute.agent.router._use_litellm_proxy", return_value=True):
            # Ollama models are not in proxy map — should use model_id directly
            result = get_litellm_model_string(QWEN3_30B_LOCAL)
            assert result == "ollama/qwen3:30b-a3b"


class TestProxyModelMap:
    def test_all_proxy_keys_exist_in_registry(self):
        """Every key in _PROXY_MODEL_MAP must be a valid model_id in ALL_MODELS."""
        for model_id in _PROXY_MODEL_MAP:
            assert model_id in ALL_MODELS, (
                f"_PROXY_MODEL_MAP key '{model_id}' not found in ALL_MODELS — "
                f"litellm_config.yaml and models.py are out of sync"
            )

    def test_all_proxy_aliases_start_with_silkroute(self):
        """All proxy aliases must follow the silkroute-* naming convention."""
        for alias in _PROXY_MODEL_MAP.values():
            assert alias.startswith("silkroute-"), f"Bad alias: {alias}"

    def test_proxy_map_has_all_tiers(self):
        """Proxy map should cover free, standard, and premium tiers."""
        aliases = set(_PROXY_MODEL_MAP.values())
        assert any("free" in a for a in aliases)
        assert any("standard" in a for a in aliases)
        assert any("premium" in a for a in aliases)
