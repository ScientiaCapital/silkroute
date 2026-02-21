"""Tests for silkroute.agent.classifier."""

from silkroute.agent.classifier import classify_task
from silkroute.config.settings import ModelTier
from silkroute.providers.models import Capability


class TestClassifyTask:
    def test_premium_security_review(self):
        result = classify_task("Perform a security review of the authentication module")
        assert result.tier == ModelTier.PREMIUM
        assert result.confidence >= 0.7

    def test_premium_architecture(self):
        result = classify_task("Architect a new microservice for payment processing")
        assert result.tier == ModelTier.PREMIUM

    def test_standard_implement(self):
        result = classify_task("Implement a new REST endpoint for user profiles")
        assert result.tier == ModelTier.STANDARD
        assert Capability.CODING in result.capabilities

    def test_free_summarize(self):
        result = classify_task("Summarize the README file")
        assert result.tier == ModelTier.FREE

    def test_free_lint(self):
        result = classify_task("Lint the Python source files")
        assert result.tier == ModelTier.FREE

    def test_default_tier_is_standard(self):
        result = classify_task("Do something vague and unclassifiable")
        assert result.tier == ModelTier.STANDARD

    def test_capability_detection_coding(self):
        result = classify_task("Write a Python function to parse CSV files")
        assert Capability.CODING in result.capabilities

    def test_capability_detection_reasoning(self):
        result = classify_task("Analyze why the tests are failing")
        assert Capability.REASONING in result.capabilities

    def test_capability_detection_tool_calling(self):
        result = classify_task("Run the test suite and read the output")
        assert Capability.TOOL_CALLING in result.capabilities

    def test_default_capabilities(self):
        # Task with no capability keywords gets CODING + TOOL_CALLING defaults
        result = classify_task("Do something completely generic")
        assert Capability.CODING in result.capabilities
        assert Capability.TOOL_CALLING in result.capabilities
