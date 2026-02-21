"""Tests for silkroute.agent.session."""

from silkroute.agent.session import AgentSession, Iteration, SessionStatus, ToolCall


class TestAgentSession:
    def test_creation_defaults(self):
        session = AgentSession(task="test task", model_id="deepseek/deepseek-v3.2")
        assert session.status == SessionStatus.ACTIVE
        assert session.iteration_count == 0
        assert session.total_cost_usd == 0.0
        assert session.project_id == "default"
        assert len(session.id) == 36  # UUID format

    def test_add_iteration_and_aggregation(self):
        session = AgentSession(task="test", model_id="test")
        session.add_iteration(Iteration(
            number=1, cost_usd=0.001, input_tokens=500, output_tokens=200,
        ))
        session.add_iteration(Iteration(
            number=2, cost_usd=0.002, input_tokens=800, output_tokens=300,
        ))
        assert session.iteration_count == 2
        assert abs(session.total_cost_usd - 0.003) < 1e-9
        assert session.total_input_tokens == 1300
        assert session.total_output_tokens == 500

    def test_complete_sets_status_and_timestamp(self):
        session = AgentSession(task="test", model_id="test")
        assert session.completed_at is None
        session.complete(SessionStatus.COMPLETED)
        assert session.status == SessionStatus.COMPLETED
        assert session.completed_at is not None

    def test_tool_call_record(self):
        tc = ToolCall(
            tool_name="shell_exec",
            tool_input={"command": "ls"},
            tool_output="file1.py\nfile2.py",
            success=True,
            duration_ms=50,
        )
        assert tc.tool_name == "shell_exec"
        assert tc.success is True
        assert tc.error_message == ""
