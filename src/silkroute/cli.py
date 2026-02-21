"""SilkRoute CLI — command-line interface for the Chinese LLM agent orchestrator.

Usage:
    silkroute init          Initialize a new project workspace
    silkroute run           Run the agent on a task
    silkroute budget        View cost tracking and budget status
    silkroute status        Check agent and provider health
    silkroute models        List available Chinese models and pricing
    silkroute daemon        Start 24/7 daemon mode
"""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from silkroute import __version__
from silkroute.config.settings import ModelTier
from silkroute.providers.models import MODELS_BY_TIER, estimate_cost

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="silkroute")
def main() -> None:
    """SilkRoute — AI agent orchestrator for Chinese LLMs.

    The fastest route from task to done — powered by China's best AI.
    """
    pass


@main.command()
@click.argument("path", default=".", type=click.Path())
def init(path: str) -> None:
    """Initialize a new SilkRoute project workspace."""
    import os
    from pathlib import Path

    workspace = Path(path).resolve()
    dirs = [
        workspace / ".silkroute",
        workspace / ".silkroute" / "sessions",
        workspace / ".silkroute" / "logs",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # Create default config if not exists
    config_path = workspace / "silkroute.toml"
    if not config_path.exists():
        config_path.write_text(_default_config())
        console.print(f"[green]✓[/green] Created {config_path}")

    env_path = workspace / ".env"
    if not env_path.exists():
        env_path.write_text(_default_env())
        console.print(f"[green]✓[/green] Created {env_path}")

    console.print(f"\n[bold green]SilkRoute workspace initialized at {workspace}[/bold green]")
    console.print("\nNext steps:")
    console.print("  1. Add your OpenRouter API key to .env")
    console.print("  2. Run: [bold]silkroute models[/bold] to see available Chinese models")
    console.print("  3. Run: [bold]silkroute run 'your task here'[/bold] to start the agent")


@main.command()
@click.argument("task", required=False)
@click.option("--model", "-m", default=None, help="Override model selection")
@click.option("--tier", "-t", type=click.Choice(["free", "standard", "premium"]), default=None)
@click.option("--project", "-p", default="default", help="Project name for cost attribution")
@click.option("--max-iterations", default=25, help="Max agent loop iterations")
def run(
    task: str | None,
    model: str | None,
    tier: str | None,
    project: str,
    max_iterations: int,
) -> None:
    """Run the SilkRoute agent on a task.

    If no task is provided, starts an interactive session.
    """
    if task:
        console.print(f"[bold]Project:[/bold] {project}")
        console.print(f"[bold]Task:[/bold] {task}")
        console.print(f"[bold]Model:[/bold] {model or 'auto-routed'}")
        console.print(f"[bold]Max iterations:[/bold] {max_iterations}")
        console.print("\n[yellow]Agent loop not yet implemented — coming in Phase 02.[/yellow]")
        console.print("Run [bold]silkroute models[/bold] to see available models.")
    else:
        console.print("[bold]Interactive mode not yet implemented.[/bold]")
        console.print("Usage: [bold]silkroute run 'describe your task here'[/bold]")


@main.command()
@click.option("--project", "-p", default=None, help="Filter by project")
@click.option("--period", type=click.Choice(["day", "week", "month"]), default="month")
def budget(project: str | None, period: str) -> None:
    """View cost tracking and budget status."""
    console.print(f"[bold]Budget Report ({period})[/bold]\n")
    console.print("[yellow]Budget tracking not yet implemented — coming in Phase 04.[/yellow]")
    console.print("\nProjected monthly costs based on model pricing:")

    table = Table(title="Cost Estimator (1000 requests/month)")
    table.add_column("Tier", style="cyan")
    table.add_column("Model", style="white")
    table.add_column("Est. Cost", style="green", justify="right")

    # Estimate: avg 2000 input tokens + 1000 output tokens per request × 1000 requests
    for tier_name, tier_enum in [("Free", ModelTier.FREE), ("Standard", ModelTier.STANDARD), ("Premium", ModelTier.PREMIUM)]:
        for model_spec in MODELS_BY_TIER[tier_enum]:
            if model_spec.provider.value == "ollama":
                continue
            cost = estimate_cost(model_spec, input_tokens=2_000_000, output_tokens=1_000_000)
            table.add_row(tier_name, model_spec.name, f"${cost:.2f}")

    console.print(table)


@main.command()
def status() -> None:
    """Check agent and provider health status."""
    console.print("[bold]SilkRoute Status[/bold]\n")
    console.print(f"  Version: {__version__}")
    console.print("  Agent: [yellow]idle[/yellow]")
    console.print("  Daemon: [dim]disabled[/dim]")
    console.print("\n[bold]Provider Health:[/bold]")
    console.print("  [yellow]Health checks not yet implemented — coming in Phase 01-02.[/yellow]")


@main.command()
@click.option("--tier", "-t", type=click.Choice(["free", "standard", "premium", "all"]), default="all")
@click.option("--capability", "-c", default=None, help="Filter by capability (coding, reasoning, tool_calling, agentic)")
def models(tier: str, capability: str | None) -> None:
    """List available Chinese models and pricing."""
    table = Table(title="SilkRoute Chinese Model Registry")
    table.add_column("Tier", style="cyan", width=10)
    table.add_column("Model", style="white", width=28)
    table.add_column("Provider", style="magenta", width=10)
    table.add_column("Input $/M", style="green", justify="right", width=10)
    table.add_column("Output $/M", style="green", justify="right", width=10)
    table.add_column("Context", justify="right", width=8)
    table.add_column("Capabilities", style="dim", width=30)
    table.add_column("MoE", justify="center", width=5)

    tiers_to_show = (
        [ModelTier.FREE, ModelTier.STANDARD, ModelTier.PREMIUM]
        if tier == "all"
        else [ModelTier(tier)]
    )

    for t in tiers_to_show:
        for m in MODELS_BY_TIER[t]:
            caps = ", ".join(c.value for c in m.capabilities)
            if capability and capability not in caps:
                continue

            input_price = "FREE" if m.is_free else f"${m.input_cost_per_m:.2f}"
            output_price = "FREE" if m.is_free else f"${m.output_cost_per_m:.2f}"
            ctx = f"{m.context_window // 1024}K"
            moe = "✓" if m.is_moe else ""
            tier_label = f"{'🟢' if t == ModelTier.FREE else '🔵' if t == ModelTier.STANDARD else '🟡'} {t.value}"

            table.add_row(tier_label, m.name, m.provider.value, input_price, output_price, ctx, caps, moe)

    console.print(table)
    console.print(
        "\n[dim]Pricing via OpenRouter (Feb 2026). "
        "Local Ollama models not shown — run [bold]silkroute models --tier free[/bold] to include.[/dim]"
    )


@main.command()
def daemon() -> None:
    """Start SilkRoute in 24/7 daemon mode."""
    console.print("[bold]SilkRoute Daemon Mode[/bold]\n")
    console.print("[yellow]Daemon mode not yet implemented — coming in Phase 07.[/yellow]")
    console.print("\nWhen ready, this will:")
    console.print("  • Listen for GitHub webhooks on port 8787")
    console.print("  • Run scheduled repo scans via cron")
    console.print("  • Send heartbeat pings every 5 minutes")
    console.print("  • Process up to 3 concurrent agent sessions")


def _default_config() -> str:
    """Generate default silkroute.toml configuration."""
    return """\
# SilkRoute Configuration
# The fastest route from task to done — powered by China's best AI.

[agent]
default_model = "deepseek/deepseek-v3.2"
free_model = "qwen/qwen3-coder:free"
premium_model = "deepseek/deepseek-r1-0528"
max_iterations = 25
timeout_seconds = 300
workspace_dir = "~/.silkroute/workspace"

[budget]
monthly_max_usd = 200.0
daily_max_usd = 10.0
default_project_budget_usd = 2.85
alert_threshold_warning = 0.50
alert_threshold_critical = 0.80

[daemon]
enabled = false
webhook_port = 8787
heartbeat_interval_seconds = 300
max_concurrent_sessions = 3
nightly_scan_cron = "0 3 * * *"

[database]
postgres_url = "postgresql://silkroute:silkroute@localhost:5432/silkroute"
redis_url = "redis://localhost:6379/0"
"""


def _default_env() -> str:
    """Generate default .env template."""
    return """\
# SilkRoute Environment Variables
# Copy this to .env and fill in your API keys

# ============================================================
# PRIMARY: OpenRouter (recommended — single key for all models)
# ============================================================
SILKROUTE_OPENROUTER_API_KEY=

# ============================================================
# OPTIONAL: Direct provider keys (bypass OpenRouter for lower latency)
# ============================================================
SILKROUTE_DEEPSEEK_API_KEY=
SILKROUTE_QWEN_API_KEY=
SILKROUTE_GLM_API_KEY=
SILKROUTE_MOONSHOT_API_KEY=

# ============================================================
# LOCAL INFERENCE (Mac Studio / NVIDIA Spark)
# ============================================================
SILKROUTE_OLLAMA_ENABLED=false
SILKROUTE_OLLAMA_BASE_URL=http://localhost:11434

# ============================================================
# ALERTS
# ============================================================
SILKROUTE_BUDGET_SLACK_WEBHOOK_URL=
SILKROUTE_BUDGET_TELEGRAM_BOT_TOKEN=
SILKROUTE_BUDGET_TELEGRAM_CHAT_ID=

# ============================================================
# HARDWARE PROFILE: mac-mini | mac-studio | nvidia-spark | hetzner-vps
# ============================================================
SILKROUTE_HARDWARE_PROFILE=mac-mini
"""


if __name__ == "__main__":
    main()
