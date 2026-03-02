"""CLI unit tests for SilkRoute — covers simple commands, skills, context7, and projects."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner

from silkroute.cli import main
from silkroute.config.settings import SilkRouteSettings

runner = CliRunner()


class TestSimpleCommands:
    def test_version(self) -> None:
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "silkroute" in result.output

    def test_status(self) -> None:
        result = runner.invoke(main, ["status"])
        assert result.exit_code == 0
        assert "Version" in result.output

    def test_models(self) -> None:
        result = runner.invoke(main, ["models"])
        assert result.exit_code == 0
        assert "DeepSeek" in result.output

    def test_models_free_tier(self) -> None:
        result = runner.invoke(main, ["models", "--tier", "free"])
        assert result.exit_code == 0
        # Free tier filter should succeed and show output
        assert result.output

    def test_models_standard_tier(self) -> None:
        result = runner.invoke(main, ["models", "--tier", "standard"])
        assert result.exit_code == 0
        assert result.output

    def test_budget(self) -> None:
        result = runner.invoke(main, ["budget"])
        assert result.exit_code == 0
        assert "Cost Estimator" in result.output

    def test_init(self, tmp_path: Path) -> None:
        result = runner.invoke(main, ["init", str(tmp_path)])
        assert result.exit_code == 0
        assert (tmp_path / ".silkroute").is_dir()
        assert (tmp_path / "silkroute.toml").exists()
        assert (tmp_path / ".env").exists()

    def test_init_creates_session_dir(self, tmp_path: Path) -> None:
        runner.invoke(main, ["init", str(tmp_path)])
        assert (tmp_path / ".silkroute" / "sessions").is_dir()

    def test_init_idempotent(self, tmp_path: Path) -> None:
        # Running init twice should not error
        runner.invoke(main, ["init", str(tmp_path)])
        result = runner.invoke(main, ["init", str(tmp_path)])
        assert result.exit_code == 0


class TestSkillsCommands:
    def test_skills_list(self) -> None:
        result = runner.invoke(main, ["skills", "list"])
        assert result.exit_code == 0
        # Table should contain skill names from register_builtin_skills
        assert "http_request" in result.output or "code_review" in result.output

    def test_skills_list_shows_all_builtins(self) -> None:
        result = runner.invoke(main, ["skills", "list"])
        assert result.exit_code == 0
        # All five builtin skills should appear
        for name in ["http_request", "search_grep", "docs_lookup", "code_review", "summarize"]:
            assert name in result.output

    def test_skills_list_category_filter(self) -> None:
        result = runner.invoke(main, ["skills", "list", "--category", "llm_native"])
        assert result.exit_code == 0
        assert "code_review" in result.output or "summarize" in result.output

    def test_skills_list_invalid_category(self) -> None:
        result = runner.invoke(main, ["skills", "list", "--category", "nonexistent"])
        assert result.exit_code == 1
        assert "Invalid category" in result.output

    def test_skills_info_code_review(self) -> None:
        result = runner.invoke(main, ["skills", "info", "code_review"])
        assert result.exit_code == 0
        assert "code_review" in result.output

    def test_skills_info_summarize(self) -> None:
        result = runner.invoke(main, ["skills", "info", "summarize"])
        assert result.exit_code == 0
        assert "summarize" in result.output

    def test_skills_info_http_request(self) -> None:
        result = runner.invoke(main, ["skills", "info", "http_request"])
        assert result.exit_code == 0
        assert "http_request" in result.output

    def test_skills_info_nonexistent(self) -> None:
        result = runner.invoke(main, ["skills", "info", "nonexistent_skill_xyz"])
        assert result.exit_code == 1
        assert "not found" in result.output


class TestContext7Commands:
    @patch("silkroute.mantis.skills.context7.Context7Client")
    def test_context7_resolve_success(self, mock_client_cls: MagicMock) -> None:
        from silkroute.mantis.skills.context7 import LibraryInfo

        mock_instance = AsyncMock()
        mock_instance.resolve_library = AsyncMock(
            return_value=LibraryInfo(
                id="lib-fastapi-123",
                name="fastapi",
                version="0.100.0",
                trust_score=0.95,
            )
        )
        mock_client_cls.return_value = mock_instance

        result = runner.invoke(main, ["context7", "resolve", "fastapi"])
        assert result.exit_code == 0
        assert "fastapi" in result.output

    @patch("silkroute.mantis.skills.context7.Context7Client")
    def test_context7_resolve_not_found(self, mock_client_cls: MagicMock) -> None:
        mock_instance = AsyncMock()
        mock_instance.resolve_library = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_instance

        result = runner.invoke(main, ["context7", "resolve", "unknown_lib_xyz"])
        assert result.exit_code == 0
        assert "not found" in result.output

    @patch("silkroute.mantis.skills.context7.Context7Client")
    def test_context7_resolve_error(self, mock_client_cls: MagicMock) -> None:
        mock_instance = AsyncMock()
        mock_instance.resolve_library = AsyncMock(side_effect=Exception("connection failed"))
        mock_client_cls.return_value = mock_instance

        result = runner.invoke(main, ["context7", "resolve", "error_lib"])
        assert result.exit_code == 1
        assert "Error" in result.output

    @patch("silkroute.mantis.skills.context7.Context7Client")
    def test_context7_query_success(self, mock_client_cls: MagicMock) -> None:
        from silkroute.mantis.skills.context7 import Context7Result, DocSnippet

        mock_instance = AsyncMock()
        mock_instance.query = AsyncMock(
            return_value=Context7Result(
                library=None,
                snippets=[
                    DocSnippet(
                        title="Getting Started",
                        content="Install with pip install fastapi",
                        url="https://fastapi.tiangolo.com",
                        relevance=0.9,
                    )
                ],
                truncated=False,
            )
        )
        mock_client_cls.return_value = mock_instance

        result = runner.invoke(main, ["context7", "query", "fastapi", "how to install"])
        assert result.exit_code == 0
        assert "Getting Started" in result.output

    @patch("silkroute.mantis.skills.context7.Context7Client")
    def test_context7_query_no_snippets(self, mock_client_cls: MagicMock) -> None:
        from silkroute.mantis.skills.context7 import Context7Result

        mock_instance = AsyncMock()
        mock_instance.query = AsyncMock(
            return_value=Context7Result(library=None, snippets=[], truncated=False)
        )
        mock_client_cls.return_value = mock_instance

        result = runner.invoke(main, ["context7", "query", "emptylib", "find nothing"])
        assert result.exit_code == 0
        assert "No documentation found" in result.output

    @patch("silkroute.mantis.skills.context7.Context7Client")
    def test_context7_query_error(self, mock_client_cls: MagicMock) -> None:
        mock_instance = AsyncMock()
        mock_instance.query = AsyncMock(side_effect=Exception("timeout"))
        mock_client_cls.return_value = mock_instance

        result = runner.invoke(main, ["context7", "query", "error_lib", "fail"])
        assert result.exit_code == 1
        assert "Error" in result.output


class TestProjectsCommands:
    def _mock_pool(self) -> MagicMock:
        pool = MagicMock()
        pool.close = AsyncMock()
        return pool

    @patch("silkroute.config.settings.load_settings")
    @patch("silkroute.db.repositories.projects.list_projects", new_callable=AsyncMock)
    @patch("asyncpg.create_pool", new_callable=AsyncMock)
    def test_projects_list(
        self,
        mock_create_pool: AsyncMock,
        mock_list_projects: AsyncMock,
        mock_load_settings: MagicMock,
        test_settings: SilkRouteSettings,
    ) -> None:
        mock_load_settings.return_value = test_settings
        mock_create_pool.return_value = self._mock_pool()
        mock_list_projects.return_value = [
            {
                "id": "proj1",
                "name": "My Project",
                "budget_monthly_usd": 2.85,
                "budget_daily_usd": 0.10,
                "github_repo": "org/repo",
            }
        ]

        result = runner.invoke(main, ["projects", "list"])
        assert result.exit_code == 0
        assert "proj1" in result.output

    @patch("silkroute.config.settings.load_settings")
    @patch("silkroute.db.repositories.projects.list_projects", new_callable=AsyncMock)
    @patch("asyncpg.create_pool", new_callable=AsyncMock)
    def test_projects_list_empty(
        self,
        mock_create_pool: AsyncMock,
        mock_list_projects: AsyncMock,
        mock_load_settings: MagicMock,
        test_settings: SilkRouteSettings,
    ) -> None:
        mock_load_settings.return_value = test_settings
        mock_create_pool.return_value = self._mock_pool()
        mock_list_projects.return_value = []

        result = runner.invoke(main, ["projects", "list"])
        assert result.exit_code == 0
        assert "No projects found" in result.output

    @patch("silkroute.config.settings.load_settings")
    @patch("silkroute.db.repositories.projects.create_project", new_callable=AsyncMock)
    @patch("asyncpg.create_pool", new_callable=AsyncMock)
    def test_projects_create(
        self,
        mock_create_pool: AsyncMock,
        mock_create_project: AsyncMock,
        mock_load_settings: MagicMock,
        test_settings: SilkRouteSettings,
    ) -> None:
        mock_load_settings.return_value = test_settings
        mock_create_pool.return_value = self._mock_pool()
        mock_create_project.return_value = {
            "id": "myproj",
            "name": "My Project",
            "budget_monthly_usd": 2.85,
            "budget_daily_usd": 0.10,
        }

        result = runner.invoke(
            main, ["projects", "create", "myproj", "--name", "My Project"]
        )
        assert result.exit_code == 0
        assert "Created" in result.output
        assert "myproj" in result.output

    @patch("silkroute.config.settings.load_settings")
    @patch("silkroute.db.repositories.projects.get_project", new_callable=AsyncMock)
    @patch("asyncpg.create_pool", new_callable=AsyncMock)
    def test_projects_show(
        self,
        mock_create_pool: AsyncMock,
        mock_get_project: AsyncMock,
        mock_load_settings: MagicMock,
        test_settings: SilkRouteSettings,
    ) -> None:
        mock_load_settings.return_value = test_settings
        mock_create_pool.return_value = self._mock_pool()
        mock_get_project.return_value = {
            "id": "myproj",
            "name": "My Project",
            "description": "A test project",
            "github_repo": "org/repo",
            "budget_monthly_usd": 2.85,
            "budget_daily_usd": 0.10,
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }

        result = runner.invoke(main, ["projects", "show", "myproj"])
        assert result.exit_code == 0
        assert "My Project" in result.output

    @patch("silkroute.config.settings.load_settings")
    @patch("silkroute.db.repositories.projects.get_project", new_callable=AsyncMock)
    @patch("asyncpg.create_pool", new_callable=AsyncMock)
    def test_projects_show_not_found(
        self,
        mock_create_pool: AsyncMock,
        mock_get_project: AsyncMock,
        mock_load_settings: MagicMock,
        test_settings: SilkRouteSettings,
    ) -> None:
        mock_load_settings.return_value = test_settings
        mock_create_pool.return_value = self._mock_pool()
        mock_get_project.return_value = None

        result = runner.invoke(main, ["projects", "show", "missing"])
        assert result.exit_code == 1
        assert "not found" in result.output

    @patch("silkroute.config.settings.load_settings")
    @patch("silkroute.db.repositories.projects.delete_project", new_callable=AsyncMock)
    @patch("asyncpg.create_pool", new_callable=AsyncMock)
    def test_projects_delete(
        self,
        mock_create_pool: AsyncMock,
        mock_delete_project: AsyncMock,
        mock_load_settings: MagicMock,
        test_settings: SilkRouteSettings,
    ) -> None:
        mock_load_settings.return_value = test_settings
        mock_create_pool.return_value = self._mock_pool()
        mock_delete_project.return_value = True

        result = runner.invoke(main, ["projects", "delete", "myproj", "--yes"])
        assert result.exit_code == 0
        assert "Deleted" in result.output

    @patch("silkroute.config.settings.load_settings")
    @patch("silkroute.db.repositories.projects.delete_project", new_callable=AsyncMock)
    @patch("asyncpg.create_pool", new_callable=AsyncMock)
    def test_projects_delete_not_found(
        self,
        mock_create_pool: AsyncMock,
        mock_delete_project: AsyncMock,
        mock_load_settings: MagicMock,
        test_settings: SilkRouteSettings,
    ) -> None:
        mock_load_settings.return_value = test_settings
        mock_create_pool.return_value = self._mock_pool()
        mock_delete_project.return_value = False

        result = runner.invoke(main, ["projects", "delete", "ghost", "--yes"])
        assert result.exit_code == 0
        assert "not found" in result.output

    @patch("silkroute.config.settings.load_settings")
    @patch("asyncpg.create_pool", new_callable=AsyncMock)
    def test_projects_list_db_error(
        self,
        mock_create_pool: AsyncMock,
        mock_load_settings: MagicMock,
        test_settings: SilkRouteSettings,
    ) -> None:
        mock_load_settings.return_value = test_settings
        mock_create_pool.side_effect = Exception("connection refused")

        result = runner.invoke(main, ["projects", "list"])
        assert result.exit_code == 1
        assert "Error" in result.output
