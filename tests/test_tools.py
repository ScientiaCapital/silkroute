"""Tests for silkroute.agent.tools."""

import pytest

from silkroute.agent.tools import (
    ToolRegistry,
    ToolSpec,
    create_default_registry,
    parse_tool_arguments,
)


class TestParseToolArguments:
    def test_valid_json(self):
        assert parse_tool_arguments('{"command": "ls"}') == {"command": "ls"}

    def test_dict_passthrough(self):
        d = {"path": "/tmp"}
        assert parse_tool_arguments(d) is d

    def test_empty_string(self):
        assert parse_tool_arguments("") == {}
        assert parse_tool_arguments("  ") == {}

    def test_markdown_fenced_json(self):
        raw = '```json\n{"command": "pwd"}\n```'
        assert parse_tool_arguments(raw) == {"command": "pwd"}

    def test_markdown_fenced_no_lang(self):
        raw = '```\n{"path": "/home"}\n```'
        assert parse_tool_arguments(raw) == {"path": "/home"}

    def test_single_quotes_repair(self):
        raw = "{'command': 'echo hello'}"
        result = parse_tool_arguments(raw)
        assert result == {"command": "echo hello"}

    def test_trailing_comma_repair(self):
        raw = '{"command": "ls", "timeout": 30,}'
        result = parse_tool_arguments(raw)
        assert result == {"command": "ls", "timeout": 30}

    def test_unparseable_returns_empty(self):
        assert parse_tool_arguments("not json at all") == {}

    def test_non_dict_json_returns_empty(self):
        assert parse_tool_arguments("[1, 2, 3]") == {}


class TestToolRegistry:
    def test_register_and_get(self):
        registry = ToolRegistry()

        async def dummy(**kwargs):
            return "ok"

        spec = ToolSpec(name="test_tool", description="A test", parameters={}, handler=dummy)
        registry.register(spec)
        assert registry.get("test_tool") is spec
        assert registry.get("nonexistent") is None

    def test_tool_names(self):
        registry = create_default_registry()
        names = registry.tool_names
        assert "shell_exec" in names
        assert "read_file" in names
        assert "write_file" in names
        assert "list_directory" in names
        assert len(names) == 8

    def test_to_openai_tools_format(self):
        registry = create_default_registry()
        tools = registry.to_openai_tools()
        assert len(tools) == 8
        for tool in tools:
            assert tool["type"] == "function"
            assert "name" in tool["function"]
            assert "description" in tool["function"]
            assert "parameters" in tool["function"]


class TestBuiltinTools:
    @pytest.mark.asyncio
    async def test_read_file_nonexistent(self):
        registry = create_default_registry()
        result = await registry.execute("read_file", {"path": "/nonexistent/file.txt"})
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_read_file_existing(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\nline3")
        registry = create_default_registry()
        result = await registry.execute("read_file", {"path": str(test_file)})
        assert "line1" in result
        assert "line3" in result

    @pytest.mark.asyncio
    async def test_write_file(self, tmp_path):
        target = tmp_path / "subdir" / "out.txt"
        registry = create_default_registry()
        result = await registry.execute("write_file", {"path": str(target), "content": "hello world"})
        assert "Successfully wrote" in result
        assert target.read_text() == "hello world"

    @pytest.mark.asyncio
    async def test_list_directory(self, tmp_path):
        (tmp_path / "file_a.txt").write_text("a")
        (tmp_path / "dir_b").mkdir()
        registry = create_default_registry()
        result = await registry.execute("list_directory", {"path": str(tmp_path)})
        assert "dir_b" in result
        assert "file_a.txt" in result

    @pytest.mark.asyncio
    async def test_shell_exec_simple(self):
        registry = create_default_registry()
        result = await registry.execute("shell_exec", {"command": "echo hello_world"})
        assert "hello_world" in result

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        registry = create_default_registry()
        result = await registry.execute("nonexistent_tool", {})
        assert "Error" in result
        assert "Unknown tool" in result


class TestSandboxedShellExec:
    """Shell exec integration with sandbox."""

    @pytest.mark.asyncio
    async def test_sandbox_blocks_dangerous_command(self, tmp_path):
        registry = create_default_registry(workspace_dir=str(tmp_path))
        result = await registry.execute("shell_exec", {"command": "sudo rm -rf /"})
        assert "blocked by sandbox" in result

    @pytest.mark.asyncio
    async def test_sandbox_allows_safe_command(self, tmp_path):
        registry = create_default_registry(workspace_dir=str(tmp_path))
        result = await registry.execute("shell_exec", {"command": "echo hello_sandbox"})
        assert "hello_sandbox" in result

    @pytest.mark.asyncio
    async def test_no_sandbox_without_workspace(self):
        registry = create_default_registry(workspace_dir=None)
        result = await registry.execute("shell_exec", {"command": "echo no_sandbox"})
        assert "no_sandbox" in result

    @pytest.mark.asyncio
    async def test_workspace_dir_sets_cwd(self, tmp_path):
        registry = create_default_registry(workspace_dir=str(tmp_path))
        result = await registry.execute("shell_exec", {"command": "pwd"})
        assert str(tmp_path) in result
