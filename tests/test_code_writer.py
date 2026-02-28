"""Tests for the Code Writer agent (mantis/agents/code_writer.py)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from silkroute.mantis.agents.code_writer import (
    CodeWriterResult,
    create_code_writer,
    run_code_writer,
)


class TestCreateCodeWriter:
    """create_code_writer() wires up deepagents correctly.

    Patches target the *source* modules because create_code_writer()
    uses local imports (from deepagents import ...) inside the function body.
    """

    @patch("silkroute.providers.openrouter.create_openrouter_model")
    @patch("deepagents.backends.LocalShellBackend")
    @patch("deepagents.create_deep_agent")
    def test_returns_agent(
        self,
        mock_create: MagicMock,
        mock_backend_cls: MagicMock,
        mock_model: MagicMock,
    ) -> None:
        mock_create.return_value = MagicMock(name="compiled_graph")
        agent = create_code_writer(api_key="sk-test")
        assert agent is mock_create.return_value

    @patch("silkroute.providers.openrouter.create_openrouter_model")
    @patch("deepagents.backends.LocalShellBackend")
    @patch("deepagents.create_deep_agent")
    def test_workspace_dir_passed_to_backend(
        self,
        mock_create: MagicMock,
        mock_backend_cls: MagicMock,
        mock_model: MagicMock,
    ) -> None:
        create_code_writer(workspace_dir="/tmp/ws", api_key="sk-test")
        mock_backend_cls.assert_called_once_with(root_dir="/tmp/ws")

    @patch("silkroute.providers.openrouter.create_openrouter_model")
    @patch("deepagents.backends.LocalShellBackend")
    @patch("deepagents.create_deep_agent")
    def test_model_override_applied(
        self,
        mock_create: MagicMock,
        mock_backend_cls: MagicMock,
        mock_model: MagicMock,
    ) -> None:
        create_code_writer(model_id="deepseek/deepseek-v3.2", api_key="sk-test")
        mock_model.assert_called_once_with(
            model_id="deepseek/deepseek-v3.2", api_key="sk-test"
        )

    @patch("silkroute.providers.openrouter.create_openrouter_model")
    @patch("deepagents.backends.LocalShellBackend")
    @patch("deepagents.create_deep_agent")
    def test_create_deep_agent_called_with_correct_args(
        self,
        mock_create: MagicMock,
        mock_backend_cls: MagicMock,
        mock_model: MagicMock,
    ) -> None:
        create_code_writer(api_key="sk-test")
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["name"] == "code-writer"
        assert "system_prompt" in call_kwargs
        assert call_kwargs["backend"] is mock_backend_cls.return_value
        assert call_kwargs["model"] is mock_model.return_value


class TestRunCodeWriter:
    """run_code_writer() handles creation + invocation + result translation."""

    @patch("silkroute.mantis.agents.code_writer.create_code_writer")
    def test_success(self, mock_create: MagicMock) -> None:
        mock_msg = MagicMock()
        mock_msg.content = "Here is the fix."
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {"messages": [mock_msg]}
        mock_create.return_value = mock_agent

        result = run_code_writer(task="Fix the bug", api_key="sk-test")

        assert isinstance(result, CodeWriterResult)
        assert result.status == "completed"
        assert result.output == "Here is the fix."
        assert result.metadata["runtime"] == "deepagents"

    @patch("silkroute.mantis.agents.code_writer.create_code_writer")
    def test_invocation_error_returns_failed(self, mock_create: MagicMock) -> None:
        mock_agent = MagicMock()
        mock_agent.invoke.side_effect = RuntimeError("model error")
        mock_create.return_value = mock_agent

        result = run_code_writer(task="Do task", api_key="sk-test")

        assert result.status == "failed"
        assert "model error" in result.error

    @patch(
        "silkroute.mantis.agents.code_writer.create_code_writer",
        side_effect=ImportError("No module named 'deepagents'"),
    )
    def test_import_error_returns_status(self, mock_create: MagicMock) -> None:
        result = run_code_writer(task="Do task", api_key="sk-test")

        assert result.status == "import_error"
        assert "deepagents" in result.error

    @patch("silkroute.mantis.agents.code_writer.create_code_writer")
    def test_empty_messages_returns_empty_output(self, mock_create: MagicMock) -> None:
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {"messages": []}
        mock_create.return_value = mock_agent

        result = run_code_writer(task="Do task", api_key="sk-test")

        assert result.status == "completed"
        assert result.output == ""

    @patch("silkroute.mantis.agents.code_writer.create_code_writer")
    def test_recursion_limit_passed(self, mock_create: MagicMock) -> None:
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {"messages": []}
        mock_create.return_value = mock_agent

        run_code_writer(task="Do task", api_key="sk-test", recursion_limit=100)

        call_args = mock_agent.invoke.call_args
        assert call_args[1]["config"]["recursion_limit"] == 100
