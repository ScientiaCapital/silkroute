"""Registry-integrity tests for silkroute.providers.models.

Distinct from test_models.py's behavioral tests (get_model, cost estimation) —
this file checks structural invariants of the registry itself.
"""

from silkroute.config.settings import ModelTier
from silkroute.providers.models import ALL_MODELS, MODELS_BY_TIER, Provider


class TestRegistryIntegrity:
    def test_no_duplicate_model_ids(self) -> None:
        ids = [model.model_id for model in ALL_MODELS.values()]
        assert len(ids) == len(set(ids))

    def test_dict_key_matches_model_id(self) -> None:
        for key, model in ALL_MODELS.items():
            assert key == model.model_id

    def test_all_local_models_are_ollama_and_free(self) -> None:
        for model in ALL_MODELS.values():
            if model.provider == Provider.OLLAMA:
                assert model.is_free is True
                assert model.input_cost_per_m == 0.0
                assert model.output_cost_per_m == 0.0

    def test_tiered_models_are_registered(self) -> None:
        tiered_ids = {
            model.model_id
            for models in MODELS_BY_TIER.values()
            for model in models
        }
        assert tiered_ids <= set(ALL_MODELS.keys())

    def test_ollama_local_model_count(self) -> None:
        local = [m for m in ALL_MODELS.values() if m.provider == Provider.OLLAMA]
        assert len(local) == 6

    def test_free_tier_includes_all_local_models(self) -> None:
        local_ids = {m.model_id for m in ALL_MODELS.values() if m.provider == Provider.OLLAMA}
        free_tier_ids = {m.model_id for m in MODELS_BY_TIER[ModelTier.FREE]}
        assert local_ids <= free_tier_ids
