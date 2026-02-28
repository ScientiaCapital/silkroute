"""Tests for global budget enforcement (daily, monthly, circuit breaker)."""

from __future__ import annotations

from silkroute.agent.cost_guard import (
    CIRCUIT_BREAKER_HOURLY_USD,
    GlobalBudgetCheck,
    check_global_budget,
)
from silkroute.config.settings import BudgetConfig


class TestCheckGlobalBudget:
    """Global budget checks: daily, monthly, circuit breaker."""

    def setup_method(self) -> None:
        self.budget_config = BudgetConfig()  # defaults: daily=10, monthly=200

    def test_all_clear(self) -> None:
        result = check_global_budget(
            daily_spent=1.0,
            monthly_spent=10.0,
            hourly_rate=0.5,
            budget_config=self.budget_config,
        )
        assert result.allowed is True
        assert result.warning == ""

    def test_monthly_exceeded(self) -> None:
        result = check_global_budget(
            daily_spent=5.0,
            monthly_spent=200.0,
            hourly_rate=0.5,
            budget_config=self.budget_config,
        )
        assert result.allowed is False
        assert "Monthly" in result.warning
        assert "200" in result.warning

    def test_daily_exceeded(self) -> None:
        result = check_global_budget(
            daily_spent=10.0,
            monthly_spent=50.0,
            hourly_rate=0.5,
            budget_config=self.budget_config,
        )
        assert result.allowed is False
        assert "Daily" in result.warning
        assert "10" in result.warning

    def test_circuit_breaker_trips(self) -> None:
        result = check_global_budget(
            daily_spent=3.0,
            monthly_spent=30.0,
            hourly_rate=3.0,  # Exceeds $2/hr threshold
            budget_config=self.budget_config,
        )
        assert result.allowed is False
        assert "CIRCUIT BREAKER" in result.warning
        assert "3.00" in result.warning

    def test_circuit_breaker_at_threshold(self) -> None:
        """At exactly the threshold, should still be allowed."""
        result = check_global_budget(
            daily_spent=1.0,
            monthly_spent=10.0,
            hourly_rate=CIRCUIT_BREAKER_HOURLY_USD,
            budget_config=self.budget_config,
        )
        assert result.allowed is True

    def test_circuit_breaker_just_over(self) -> None:
        result = check_global_budget(
            daily_spent=1.0,
            monthly_spent=10.0,
            hourly_rate=CIRCUIT_BREAKER_HOURLY_USD + 0.01,
            budget_config=self.budget_config,
        )
        assert result.allowed is False
        assert "CIRCUIT BREAKER" in result.warning

    def test_monthly_warning_threshold(self) -> None:
        result = check_global_budget(
            daily_spent=1.0,
            monthly_spent=110.0,  # 55% of 200
            hourly_rate=0.5,
            budget_config=self.budget_config,
        )
        assert result.allowed is True
        assert "WARNING" in result.warning
        assert "55%" in result.warning

    def test_monthly_critical_threshold(self) -> None:
        result = check_global_budget(
            daily_spent=1.0,
            monthly_spent=170.0,  # 85% of 200
            hourly_rate=0.5,
            budget_config=self.budget_config,
        )
        assert result.allowed is True
        assert "CRITICAL" in result.warning
        assert "85%" in result.warning

    def test_circuit_breaker_takes_priority(self) -> None:
        """Even if daily/monthly are fine, circuit breaker halts."""
        result = check_global_budget(
            daily_spent=1.0,
            monthly_spent=10.0,
            hourly_rate=5.0,
            budget_config=self.budget_config,
        )
        assert result.allowed is False
        assert "CIRCUIT BREAKER" in result.warning

    def test_custom_budget_limits(self) -> None:
        """Custom BudgetConfig with lower limits."""
        config = BudgetConfig(daily_max_usd=5.0, monthly_max_usd=100.0)
        result = check_global_budget(
            daily_spent=5.0,
            monthly_spent=50.0,
            hourly_rate=0.5,
            budget_config=config,
        )
        assert result.allowed is False
        assert "Daily" in result.warning


class TestGlobalBudgetCheckDataclass:
    """GlobalBudgetCheck fields."""

    def test_fields(self) -> None:
        check = GlobalBudgetCheck(
            allowed=True,
            daily_spent_usd=1.5,
            daily_limit_usd=10.0,
            monthly_spent_usd=50.0,
            monthly_limit_usd=200.0,
            hourly_rate_usd=0.3,
            warning="test warning",
        )
        assert check.daily_spent_usd == 1.5
        assert check.monthly_limit_usd == 200.0
        assert check.hourly_rate_usd == 0.3
