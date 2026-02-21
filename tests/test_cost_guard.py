"""Tests for silkroute.agent.cost_guard."""

from silkroute.agent.cost_guard import check_budget
from silkroute.agent.session import AgentSession, Iteration
from silkroute.config.settings import BudgetConfig
from silkroute.providers.models import get_model


class TestCheckBudget:
    def setup_method(self):
        self.model = get_model("deepseek/deepseek-v3.2")
        self.budget_config = BudgetConfig()

    def test_fresh_session_allowed(self):
        session = AgentSession(task="test", model_id="test", budget_limit_usd=1.0)
        result = check_budget(session, self.model, self.budget_config)
        assert result.allowed is True
        assert result.spent_usd == 0.0
        assert result.remaining_usd == 1.0

    def test_budget_exceeded(self):
        session = AgentSession(task="test", model_id="test", budget_limit_usd=0.001)
        # Add iteration that used up the budget
        session.add_iteration(Iteration(number=1, cost_usd=0.001))
        result = check_budget(session, self.model, self.budget_config)
        assert result.allowed is False
        assert "exhausted" in result.warning.lower()

    def test_warning_threshold(self):
        session = AgentSession(task="test", model_id="test", budget_limit_usd=1.0)
        # Spend 55% of budget → should trigger warning (threshold=0.50)
        session.add_iteration(Iteration(number=1, cost_usd=0.55))
        result = check_budget(session, self.model, self.budget_config)
        assert result.allowed is True
        assert "WARNING" in result.warning

    def test_critical_threshold(self):
        session = AgentSession(task="test", model_id="test", budget_limit_usd=1.0)
        # Spend 85% of budget → should trigger critical (threshold=0.80)
        session.add_iteration(Iteration(number=1, cost_usd=0.85))
        result = check_budget(session, self.model, self.budget_config)
        assert result.allowed is True
        assert "CRITICAL" in result.warning

    def test_no_warning_below_threshold(self):
        session = AgentSession(task="test", model_id="test", budget_limit_usd=1.0)
        session.add_iteration(Iteration(number=1, cost_usd=0.10))
        result = check_budget(session, self.model, self.budget_config)
        assert result.allowed is True
        assert result.warning == ""
