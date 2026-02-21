"""Tests for silkroute.config.settings."""
import pytest
from silkroute.config.settings import ModelTier, HardwareProfile, BudgetConfig

class TestModelTier:
    def test_tier_values(self):
        assert ModelTier.FREE.value == "free"
        assert ModelTier.STANDARD.value == "standard"
        assert ModelTier.PREMIUM.value == "premium"

    def test_tier_from_string(self):
        assert ModelTier("free") == ModelTier.FREE

class TestHardwareProfile:
    def test_profiles(self):
        assert HardwareProfile.MAC_MINI.value == "mac-mini"
        assert HardwareProfile.MAC_STUDIO.value == "mac-studio"

class TestBudgetConfig:
    def test_defaults(self):
        config = BudgetConfig()
        assert config.monthly_max_usd == 200.0
        assert config.daily_max_usd == 10.0
        assert config.default_project_budget_usd == 2.85
        assert config.alert_threshold_warning == 0.50
        assert config.alert_threshold_critical == 0.80
