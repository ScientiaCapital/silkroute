"""SilkRoute configuration system.

Loads settings from environment variables, .env files, and silkroute.toml.
Chinese model providers are configured as first-class defaults.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelTier(StrEnum):
    """LLM routing tiers — maps task complexity to cost level."""

    FREE = "free"
    STANDARD = "standard"
    PREMIUM = "premium"


class HardwareProfile(StrEnum):
    """Deployment hardware profiles for resource allocation."""

    MAC_MINI = "mac-mini"
    MAC_STUDIO = "mac-studio"
    NVIDIA_SPARK = "nvidia-spark"
    HETZNER_VPS = "hetzner-vps"
    CUSTOM = "custom"


class ProviderConfig(BaseSettings):
    """Chinese LLM provider API keys and endpoints."""

    model_config = SettingsConfigDict(env_prefix="SILKROUTE_")

    # Primary gateway (recommended)
    openrouter_api_key: str = Field(default="", description="OpenRouter unified API key")

    # Direct Chinese provider keys (optional, bypass OpenRouter markup)
    deepseek_api_key: str = Field(default="", description="DeepSeek direct API key")
    qwen_api_key: str = Field(default="", description="Alibaba DashScope API key")
    glm_api_key: str = Field(default="", description="Zhipu AI (GLM) API key")
    moonshot_api_key: str = Field(default="", description="Moonshot AI (Kimi) API key")

    # Local inference
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Ollama local inference endpoint",
    )
    ollama_enabled: bool = Field(
        default=False,
        description="Enable Ollama for local model routing",
    )

    # LiteLLM proxy
    use_litellm_proxy: bool = Field(
        default=False,
        description="Route through LiteLLM proxy at localhost:4000",
    )


class BudgetConfig(BaseSettings):
    """Per-project and global budget governance."""

    model_config = SettingsConfigDict(env_prefix="SILKROUTE_BUDGET_")

    # Global limits
    monthly_max_usd: float = Field(default=200.0, description="Hard monthly budget cap in USD")
    daily_max_usd: float = Field(default=10.0, description="Daily budget pacing cap")

    # Alert thresholds (percentage of monthly budget)
    alert_threshold_warning: float = Field(default=0.50, description="Slack alert at 50%")
    alert_threshold_critical: float = Field(default=0.80, description="Slack alert at 80%")
    alert_threshold_shutdown: float = Field(default=1.00, description="Hard stop at 100%")

    # Per-project defaults
    default_project_budget_usd: float = Field(
        default=2.85,
        description="Default per-project monthly budget ($200 / 70 repos)",
    )

    # Alert destinations
    slack_webhook_url: str = Field(default="", description="Slack webhook for budget alerts")
    telegram_bot_token: str = Field(default="", description="Telegram bot token for alerts")
    telegram_chat_id: str = Field(default="", description="Telegram chat ID for alerts")


class AgentConfig(BaseSettings):
    """Core agent behavior settings."""

    model_config = SettingsConfigDict(env_prefix="SILKROUTE_AGENT_")

    # Model defaults
    default_model: str = Field(
        default="deepseek/deepseek-v3.2",
        description="Default model for standard tasks",
    )
    free_model: str = Field(
        default="qwen/qwen3-coder:free",
        description="Free-tier model for simple tasks",
    )
    premium_model: str = Field(
        default="deepseek/deepseek-r1-0528",
        description="Premium model for complex reasoning",
    )

    # Execution limits
    max_iterations: int = Field(default=25, description="Max ReAct loop iterations per task")
    max_tool_calls_per_iteration: int = Field(default=5, description="Max tools per step")
    timeout_seconds: int = Field(default=300, description="Per-task timeout")

    # Workspace
    workspace_dir: str = Field(
        default="~/.silkroute/workspace",
        description="Agent workspace root directory",
    )

    # Session persistence
    persist_sessions: bool = Field(default=True, description="Save session state to PostgreSQL")


class DaemonConfig(BaseSettings):
    """24/7 daemon mode configuration."""

    model_config = SettingsConfigDict(env_prefix="SILKROUTE_DAEMON_")

    enabled: bool = Field(default=False, description="Run as persistent daemon")
    heartbeat_interval_seconds: int = Field(default=300, description="Health check ping interval")
    webhook_port: int = Field(default=8787, description="GitHub webhook listener port")
    max_concurrent_sessions: int = Field(default=3, description="Parallel agent sessions")

    # Unix socket and PID file paths
    socket_path: str = Field(
        default="~/.silkroute/daemon.sock",
        description="Unix socket path for daemon IPC",
    )
    pid_file: str = Field(
        default="~/.silkroute/daemon.pid",
        description="PID file to prevent duplicate daemon instances",
    )

    # Scheduled tasks
    nightly_scan_enabled: bool = Field(default=True, description="Run nightly repo scans")
    nightly_scan_cron: str = Field(default="0 3 * * *", description="Cron for nightly scan (3 AM)")
    dependency_check_cron: str = Field(
        default="0 6 * * 1",
        description="Weekly dependency audit (Monday 6 AM)",
    )
    budget_rollup_cron: str = Field(
        default="5 0 * * *",
        description="Daily budget snapshot rollup (12:05 AM)",
    )


class MantisConfig(BaseSettings):
    """Mantis multi-agent framework settings."""

    model_config = SettingsConfigDict(env_prefix="SILKROUTE_MANTIS_")

    runtime: str = Field(default="legacy", description="Runtime backend: legacy | deepagents")
    default_model: str = Field(
        default="deepseek/deepseek-v3.2",
        description="Default model for Mantis agents",
    )
    code_writer_model: str = Field(
        default="qwen/qwen3-coder",
        description="Model for code writing tasks",
    )
    max_iterations: int = Field(
        default=50,
        description="Max recursion limit for Deep Agents (LangGraph recursion_limit)",
    )
    budget_limit_usd: float = Field(default=5.0, description="Per-task budget cap in USD")
    default_backend: str = Field(
        default="local_shell",
        description="Deep Agents backend: local_shell | filesystem | state",
    )
    enable_subagents: bool = Field(
        default=False, description="Enable sub-agent spawning (Phase 2+)"
    )
    orchestrator_max_sub_tasks: int = Field(
        default=5, description="Max sub-tasks per orchestration"
    )
    orchestrator_stage_timeout_seconds: int = Field(
        default=120, description="Timeout per orchestrator stage in seconds"
    )


class SupervisorConfig(BaseSettings):
    """Supervisor and Ralph Mode configuration."""

    model_config = SettingsConfigDict(env_prefix="SILKROUTE_SUPERVISOR_")

    enabled: bool = Field(default=False, description="Enable supervisor runtime")
    max_steps: int = Field(default=20, description="Max steps per supervisor plan")
    step_timeout_seconds: int = Field(default=300, description="Per-step timeout")
    session_timeout_seconds: int = Field(default=3600, description="Per-session timeout")
    checkpoint_enabled: bool = Field(default=True, description="Persist checkpoints to DB")
    max_retries: int = Field(default=2, description="Default step retry count")
    retry_backoff_seconds: float = Field(default=5.0, description="Base retry backoff")
    ralph_cron: str = Field(default="*/30 * * * *", description="Ralph Mode cron schedule")
    ralph_budget_usd: float = Field(default=5.0, description="Per-cycle Ralph budget")


class SkillsConfig(BaseSettings):
    """Skills framework configuration."""

    model_config = SettingsConfigDict(env_prefix="SILKROUTE_SKILLS_")

    enabled: bool = Field(default=True, description="Enable skills framework")
    max_concurrent_skills: int = Field(default=3, description="Max concurrent skill executions")
    default_budget_usd: float = Field(default=0.50, description="Default per-skill budget cap")
    llm_model: str = Field(
        default="deepseek/deepseek-r1-0528:free",
        description="Default model for LLM-native skills",
    )


class Context7Config(BaseSettings):
    """Context7 documentation API configuration."""

    model_config = SettingsConfigDict(env_prefix="SILKROUTE_CONTEXT7_")

    api_key: str = Field(
        default="", description="Context7 API key (optional, for higher rate limits)"
    )
    base_url: str = Field(default="https://context7.com", description="Context7 API base URL")
    timeout_seconds: int = Field(default=10, description="HTTP timeout for Context7 requests")
    max_snippets: int = Field(default=20, description="Max documentation snippets to return")
    max_context_tokens: int = Field(default=8000, description="Max tokens for context injection")
    max_concurrent_requests: int = Field(default=3, description="Max concurrent Context7 requests")


class ApiConfig(BaseSettings):
    """FastAPI REST layer configuration."""

    model_config = SettingsConfigDict(env_prefix="SILKROUTE_API_")

    host: str = Field(default="0.0.0.0", description="API bind address")
    port: int = Field(default=8787, description="API listen port")
    api_key: str = Field(default="", description="Bearer token for auth (empty = disabled)")
    cors_origins: list[str] = Field(
        default=["http://localhost:3000"],
        description="Allowed CORS origins",
    )
    queue_maxsize: int = Field(default=100, description="Max pending tasks in queue")
    stream_timeout_seconds: int = Field(
        default=300, description="Server-side SSE stream timeout"
    )


class DatabaseConfig(BaseSettings):
    """PostgreSQL and Redis connection settings."""

    model_config = SettingsConfigDict(env_prefix="SILKROUTE_DB_")

    postgres_url: str = Field(
        default="postgresql://silkroute:silkroute@localhost:5432/silkroute",
        description="PostgreSQL connection string",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection string",
    )


class SilkRouteSettings(BaseSettings):
    """Root configuration — aggregates all sub-configs."""

    model_config = SettingsConfigDict(
        env_prefix="SILKROUTE_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Sub-configurations
    providers: ProviderConfig = Field(default_factory=ProviderConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    daemon: DaemonConfig = Field(default_factory=DaemonConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    mantis: MantisConfig = Field(default_factory=MantisConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    supervisor: SupervisorConfig = Field(default_factory=SupervisorConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    context7: Context7Config = Field(default_factory=Context7Config)

    # Global
    hardware_profile: HardwareProfile = Field(
        default=HardwareProfile.MAC_MINI,
        description="Hardware deployment profile",
    )
    log_level: str = Field(default="INFO", description="Logging level")
    litellm_config_path: str = Field(
        default="litellm_config.yaml",
        description="Path to LiteLLM proxy configuration",
    )

    @model_validator(mode="after")
    def validate_at_least_one_provider(self) -> SilkRouteSettings:
        """Ensure at least one LLM provider is configured."""
        has_provider = any([
            self.providers.openrouter_api_key,
            self.providers.deepseek_api_key,
            self.providers.qwen_api_key,
            self.providers.glm_api_key,
            self.providers.moonshot_api_key,
            self.providers.ollama_enabled,
        ])
        if not has_provider:
            raise ValueError(
                "At least one LLM provider must be configured. "
                "Set SILKROUTE_OPENROUTER_API_KEY for the easiest setup, "
                "or enable Ollama with SILKROUTE_OLLAMA_ENABLED=true for local inference."
            )
        return self


def load_settings() -> SilkRouteSettings:
    """Load SilkRoute settings from environment and config files."""
    return SilkRouteSettings()
