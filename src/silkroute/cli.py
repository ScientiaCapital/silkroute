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
@click.option("--budget", "-b", default=10.0, type=float, help="Session budget cap in USD")
def run(
    task: str | None,
    model: str | None,
    tier: str | None,
    project: str,
    max_iterations: int,
    budget: float,
) -> None:
    """Run the SilkRoute agent on a task.

    If no task is provided, starts an interactive session.
    """
    if not task:
        console.print("[bold]Interactive mode not yet implemented.[/bold]")
        console.print("Usage: [bold]silkroute run 'describe your task here'[/bold]")
        return

    import asyncio

    from silkroute.agent import run_agent

    try:
        asyncio.run(run_agent(
            task,
            model_override=model,
            tier_override=tier,
            project_id=project,
            max_iterations=max_iterations,
            budget_limit_usd=budget,
        ))
    except KeyboardInterrupt:
        console.print("\n[yellow]Agent interrupted by user.[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Agent error: {e}[/red]")
        raise SystemExit(1) from e


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

    # Estimate: avg 2000 input + 1000 output tokens per request * 1000 requests
    tier_pairs = [
        ("Free", ModelTier.FREE),
        ("Standard", ModelTier.STANDARD),
        ("Premium", ModelTier.PREMIUM),
    ]
    for tier_name, tier_enum in tier_pairs:
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
@click.option(
    "--tier", "-t",
    type=click.Choice(["free", "standard", "premium", "all"]),
    default="all",
)
@click.option(
    "--capability", "-c",
    default=None,
    help="Filter by capability (coding, reasoning, tool_calling, agentic)",
)
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
            icon = "🟢" if t == ModelTier.FREE else (
                "🔵" if t == ModelTier.STANDARD else "🟡"
            )
            tier_label = f"{icon} {t.value}"

            table.add_row(
                tier_label, m.name, m.provider.value,
                input_price, output_price, ctx, caps, moe,
            )

    console.print(table)
    console.print(
        "\n[dim]Pricing via OpenRouter (Feb 2026). "
        "Local Ollama models not shown — run "
        "[bold]silkroute models --tier free[/bold] "
        "to include.[/dim]"
    )


@main.command()
@click.option("--host", default="0.0.0.0", help="Bind address")
@click.option("--port", "-p", default=8787, type=int, help="Listen port")
@click.option("--reload", is_flag=True, default=False, help="Enable auto-reload (dev)")
def api(host: str, port: int, reload: bool) -> None:
    """Start the SilkRoute REST API server.

    Launches a FastAPI server via uvicorn at the given host:port.
    Swagger docs available at http://{host}:{port}/docs
    """
    import uvicorn

    console.print("[bold]SilkRoute API Server[/bold]")
    console.print(f"  Host: {host}")
    console.print(f"  Port: {port}")
    console.print(f"  Docs: http://{host}:{port}/docs")
    console.print()

    uvicorn.run(
        "silkroute.api.app:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )


@main.group(invoke_without_command=True)
@click.option("--foreground", "-f", is_flag=True, default=True, help="Run in foreground (default)")
@click.pass_context
def daemon(ctx: click.Context, foreground: bool) -> None:
    """Start SilkRoute in 24/7 daemon mode.

    When invoked without a subcommand, starts the daemon server.
    Use subcommands (submit, status, stop) to interact with a running daemon.
    """
    if ctx.invoked_subcommand is not None:
        return  # Subcommand will handle it

    import asyncio

    from silkroute.config.settings import DaemonConfig
    from silkroute.daemon.server import DaemonServer

    config = DaemonConfig()
    server = DaemonServer(config)

    console.print("[bold]SilkRoute Daemon Mode[/bold]")
    console.print(f"  Socket: {config.socket_path}")
    console.print(f"  Workers: {config.max_concurrent_sessions}")
    console.print(f"  Heartbeat: every {config.heartbeat_interval_seconds}s")
    console.print()

    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        console.print("\n[yellow]Daemon interrupted.[/yellow]")


@daemon.command("submit")
@click.argument("task")
@click.option("--project", "-p", default="default", help="Project name")
@click.option("--tier", "-t", type=click.Choice(["free", "standard", "premium"]), default=None)
@click.option("--model", "-m", default=None, help="Override model selection")
def daemon_submit(task: str, project: str, tier: str | None, model: str | None) -> None:
    """Submit a task to the running daemon."""
    import asyncio
    import json
    from pathlib import Path

    from silkroute.config.settings import DaemonConfig

    config = DaemonConfig()

    async def _submit() -> dict:
        socket_path = Path(config.socket_path).expanduser()
        if not socket_path.exists():
            return {"ok": False, "error": f"Daemon not running (no socket at {socket_path})"}

        reader, writer = await asyncio.open_unix_connection(str(socket_path))
        msg = {
            "action": "submit",
            "task": {
                "task": task,
                "project_id": project,
                "tier_override": tier,
                "model_override": model,
            },
        }
        writer.write(json.dumps(msg).encode())
        await writer.drain()
        writer.write_eof()

        data = await reader.read(65536)
        writer.close()
        await writer.wait_closed()
        return json.loads(data.decode())

    result = asyncio.run(_submit())
    if result.get("ok"):
        console.print(f"[green]Task submitted:[/green] {result['id']}")
    else:
        console.print(f"[red]Error:[/red] {result.get('error', 'Unknown error')}")
        raise SystemExit(1)


@daemon.command("status")
def daemon_status() -> None:
    """Query the running daemon's status."""
    import asyncio
    import json
    from pathlib import Path

    from silkroute.config.settings import DaemonConfig

    config = DaemonConfig()

    async def _status() -> dict:
        socket_path = Path(config.socket_path).expanduser()
        if not socket_path.exists():
            return {"running": False, "error": f"Daemon not running (no socket at {socket_path})"}

        reader, writer = await asyncio.open_unix_connection(str(socket_path))
        writer.write(json.dumps({"action": "status"}).encode())
        await writer.drain()
        writer.write_eof()

        data = await reader.read(65536)
        writer.close()
        await writer.wait_closed()
        return json.loads(data.decode())

    status = asyncio.run(_status())
    if status.get("running"):
        console.print("[bold]SilkRoute Daemon Status[/bold]\n")
        console.print("  Status: [green]running[/green]")
        console.print(f"  Uptime: {status.get('uptime_seconds', 0)}s")
        active = status.get("active_workers", 0)
        mx = status.get("max_workers", 0)
        console.print(f"  Workers: {active}/{mx}")
        console.print(f"  Queue: {status.get('pending', 0)} pending")
        submitted = status.get("total_submitted", 0)
        completed = status.get("total_completed", 0)
        console.print(f"  Tasks: {submitted} submitted, {completed} completed")
    else:
        console.print("[yellow]Daemon not running.[/yellow]")
        if "error" in status:
            console.print(f"  {status['error']}")


@daemon.command("stop")
def daemon_stop() -> None:
    """Stop the running daemon gracefully."""
    import asyncio
    import json
    from pathlib import Path

    from silkroute.config.settings import DaemonConfig

    config = DaemonConfig()

    async def _stop() -> dict:
        socket_path = Path(config.socket_path).expanduser()
        if not socket_path.exists():
            return {"ok": False, "error": f"Daemon not running (no socket at {socket_path})"}

        reader, writer = await asyncio.open_unix_connection(str(socket_path))
        writer.write(json.dumps({"action": "stop"}).encode())
        await writer.drain()
        writer.write_eof()

        data = await reader.read(65536)
        writer.close()
        await writer.wait_closed()
        return json.loads(data.decode())

    result = asyncio.run(_stop())
    if result.get("ok"):
        console.print("[green]Daemon stop requested. Shutting down gracefully...[/green]")
    else:
        console.print(f"[red]Error:[/red] {result.get('error', 'Unknown error')}")
        raise SystemExit(1)


@main.group()
def supervisor() -> None:
    """Manage supervisor workflows (long-running compound tasks)."""
    pass


@supervisor.command("create")
@click.argument("description")
@click.option("--project", "-p", default="default", help="Project ID")
@click.option("--budget", "-b", default=10.0, type=float, help="Total budget in USD")
def supervisor_create(description: str, project: str, budget: float) -> None:
    """Create and execute a supervisor session.

    DESCRIPTION: Task description (use numbered steps: "1. review 2. fix 3. test")
    """
    import asyncio

    from silkroute.mantis.runtime.interface import AgentResult, RuntimeConfig
    from silkroute.mantis.supervisor.runtime import SupervisorRuntime

    rt = SupervisorRuntime()

    async def _run() -> AgentResult:
        result = await rt.invoke(
            description,
            RuntimeConfig(project_id=project, budget_limit_usd=budget),
        )
        return result

    try:
        result = asyncio.run(_run())
        if result.success:
            console.print(f"[green]Session completed[/green]: {result.session_id}")
            console.print(f"  Steps: {result.metadata.get('step_count', 0)}")
            console.print(f"  Cost: ${result.cost_usd:.4f}")
            if result.output:
                console.print(f"\n[bold]Output:[/bold]\n{result.output[:500]}")
        else:
            console.print(f"[red]Session failed[/red]: {result.error}")
            raise SystemExit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Supervisor interrupted.[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Supervisor error: {e}[/red]")
        raise SystemExit(1) from e


@supervisor.command("status")
@click.option("--session-id", "-s", default=None, help="Session ID to query")
def supervisor_status(session_id: str | None) -> None:
    """Show supervisor session status."""
    if session_id:
        console.print(f"[bold]Supervisor Session: {session_id}[/bold]")
        console.print("[yellow]Session query requires database — use the API instead.[/yellow]")
        console.print(f"  curl http://localhost:8787/supervisor/sessions/{session_id}")
    else:
        console.print("[bold]Supervisor Status[/bold]")
        console.print("  Use --session-id to query a specific session,")
        console.print("  or the API: curl http://localhost:8787/supervisor/sessions")


@supervisor.command("resume")
@click.argument("session_id")
def supervisor_resume(session_id: str) -> None:
    """Resume a paused or failed supervisor session."""
    console.print(f"[bold]Resuming session: {session_id}[/bold]")
    console.print("[yellow]Resume requires database — use the API:[/yellow]")
    console.print(f"  curl -X POST http://localhost:8787/supervisor/sessions/{session_id}/resume")


@supervisor.command("cancel")
@click.argument("session_id")
def supervisor_cancel(session_id: str) -> None:
    """Cancel a supervisor session."""
    console.print(f"[bold]Cancelling session: {session_id}[/bold]")
    console.print("[yellow]Cancel requires database — use the API:[/yellow]")
    console.print(f"  curl -X DELETE http://localhost:8787/supervisor/sessions/{session_id}")


@supervisor.command("ralph")
@click.option("--once", is_flag=True, default=False, help="Run one cycle and exit")
def supervisor_ralph(once: bool) -> None:
    """Start Ralph Mode (autonomous supervisor loop).

    By default, starts as a scheduled cron job via the daemon scheduler.
    Use --once to run a single cycle and exit.
    """
    import asyncio

    if once:
        from silkroute.config.settings import BudgetConfig, SupervisorConfig
        from silkroute.mantis.supervisor.ralph import RalphController

        controller = RalphController(
            supervisor_config=SupervisorConfig(enabled=True),
            budget_config=BudgetConfig(),
        )

        console.print("[bold]Ralph Mode — single cycle[/bold]")
        try:
            result = asyncio.run(controller.run_cycle())
            console.print(f"  Status: {result.get('status', 'unknown')}")
            if result.get("plans_executed"):
                console.print(f"  Plans executed: {result['plans_executed']}")
        except KeyboardInterrupt:
            console.print("\n[yellow]Ralph cycle interrupted.[/yellow]")
    else:
        console.print("[bold]Ralph Mode[/bold]")
        console.print("  Ralph Mode runs as part of the daemon scheduler.")
        console.print("  Enable with: SILKROUTE_SUPERVISOR_ENABLED=true")
        console.print("  Start daemon: silkroute daemon")


@main.group()
def skills() -> None:
    """Manage skills and capabilities."""
    pass


@skills.command("list")
@click.option("--category", "-c", default=None, help="Filter by category")
def skills_list(category: str | None) -> None:
    """List all available skills."""
    from silkroute.mantis.skills import SkillCategory, SkillRegistry
    from silkroute.mantis.skills.builtin import register_builtin_skills

    registry = SkillRegistry()
    register_builtin_skills(registry)

    cat_filter: SkillCategory | None = None
    if category is not None:
        try:
            cat_filter = SkillCategory(category)
        except ValueError:
            console.print(f"[red]Invalid category '{category}'.[/red]")
            valid = ", ".join(c.value for c in SkillCategory)
            console.print(f"  Valid values: {valid}")
            raise SystemExit(1) from None

    skill_list = registry.list_skills(category=cat_filter)

    table = Table(title="SilkRoute Skills")
    table.add_column("Name", style="cyan")
    table.add_column("Category", style="magenta")
    table.add_column("LLM", justify="center")
    table.add_column("Budget", style="green", justify="right")
    table.add_column("Description", style="dim", width=40)

    for s in skill_list:
        llm_icon = "✓" if s.is_llm_native else ""
        table.add_row(
            s.name,
            s.category.value,
            llm_icon,
            f"${s.max_budget_usd:.2f}",
            s.description[:40],
        )

    console.print(table)


@skills.command("info")
@click.argument("skill_name")
def skills_info(skill_name: str) -> None:
    """Show detailed info for a specific skill."""
    from silkroute.mantis.skills import SkillRegistry
    from silkroute.mantis.skills.builtin import register_builtin_skills

    registry = SkillRegistry()
    register_builtin_skills(registry)

    skill = registry.get(skill_name)
    if skill is None:
        console.print(f"[red]Skill '{skill_name}' not found.[/red]")
        raise SystemExit(1)

    console.print(f"[bold]{skill.name}[/bold] v{skill.version}")
    console.print(f"  Category: [magenta]{skill.category.value}[/magenta]")
    console.print(f"  Description: {skill.description}")
    console.print(f"  LLM Native: {'Yes' if skill.is_llm_native else 'No'}")
    if skill.model_hint:
        console.print(f"  Model: {skill.model_hint}")
    console.print(f"  Budget: ${skill.max_budget_usd:.2f}/invocation")
    if skill.required_tools:
        console.print(f"  Required Tools: {', '.join(skill.required_tools)}")
    if skill.parameters:
        import json
        console.print(f"  Parameters: {json.dumps(skill.parameters, indent=2)}")


@main.group()
def context7() -> None:
    """Query Context7 for library documentation."""
    pass


@context7.command("resolve")
@click.argument("library_name")
@click.option("--query", "-q", default="", help="Optional search query")
def context7_resolve(library_name: str, query: str) -> None:
    """Resolve a library name to a Context7 library ID."""
    import asyncio

    from silkroute.config.settings import Context7Config
    from silkroute.mantis.skills.context7 import Context7Client

    cfg = Context7Config()
    client = Context7Client(
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        timeout=cfg.timeout_seconds,
    )

    async def _resolve() -> object:
        return await client.resolve_library(library_name, query)

    try:
        lib = asyncio.run(_resolve())
        if lib is None:
            console.print(f"[yellow]Library '{library_name}' not found on Context7.[/yellow]")
            return
        console.print(f"[green]Found:[/green] {lib.name}")
        console.print(f"  ID: {lib.id}")
        console.print(f"  Version: {lib.version}")
        console.print(f"  Trust Score: {lib.trust_score:.2f}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1) from e


@context7.command("query")
@click.argument("library_name")
@click.argument("query")
def context7_query(library_name: str, query: str) -> None:
    """Query Context7 for library documentation."""
    import asyncio

    from silkroute.config.settings import Context7Config
    from silkroute.mantis.skills.context7 import Context7Client

    cfg = Context7Config()
    client = Context7Client(
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        timeout=cfg.timeout_seconds,
        max_snippets=cfg.max_snippets,
        max_context_tokens=cfg.max_context_tokens,
    )

    async def _query() -> object:
        return await client.query(library_name, query)

    try:
        result = asyncio.run(_query())
        if not result.snippets:
            console.print(f"[yellow]No documentation found for '{library_name}': {query}[/yellow]")
            return
        console.print(f"[bold]Context7 Results for {library_name}[/bold]")
        console.print(f"  Snippets: {len(result.snippets)}")
        if result.truncated:
            console.print("  [yellow](truncated)[/yellow]")
        console.print()
        for i, snippet in enumerate(result.snippets[:5], 1):
            console.print(f"[cyan]--- {i}. {snippet.title} ---[/cyan]")
            console.print(snippet.content[:500])
            if snippet.url:
                console.print(f"  [dim]{snippet.url}[/dim]")
            console.print()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1) from e


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
