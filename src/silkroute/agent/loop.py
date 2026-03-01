"""Core ReAct agent loop — the Think → Act → Observe cycle.

Orchestrates classification, model selection, tool execution, cost tracking,
and Rich terminal output for a single agent run.

Database persistence is optional: if PostgreSQL is unavailable, the agent
continues running and logs a warning. All DB calls are wrapped in try/except.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import asyncpg
import litellm
import structlog
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from silkroute.agent.classifier import classify_task
from silkroute.agent.cost_guard import check_budget, check_global_budget
from silkroute.agent.prompts import build_system_prompt
from silkroute.agent.router import get_litellm_model_string, select_model
from silkroute.agent.session import AgentSession, Iteration, SessionStatus, ToolCall
from silkroute.agent.tools import create_default_registry, parse_tool_arguments
from silkroute.config.settings import AgentConfig, BudgetConfig, ModelTier
from silkroute.providers.models import ModelSpec, estimate_cost

log = structlog.get_logger()
console = Console()


async def run_agent(
    task: str,
    *,
    model_override: str | None = None,
    tier_override: str | None = None,
    project_id: str = "default",
    max_iterations: int = 25,
    budget_limit_usd: float = 10.0,
    workspace_dir: str | None = None,
    daemon_mode: bool = False,
    stream_queue: asyncio.Queue[str | None] | None = None,
) -> AgentSession:
    """Run the ReAct agent loop on a task.

    Args:
        stream_queue: If provided, per-iteration JSON events are pushed to
            this queue for real-time streaming. A None sentinel is pushed
            when the loop finishes.

    Returns an AgentSession with full history of iterations, tool calls, and costs.
    """
    # Resolve workspace
    if workspace_dir is None:
        workspace_dir = os.getcwd()
    workspace_dir = str(Path(workspace_dir).expanduser().resolve())

    # Step 1: Classify task
    classification = classify_task(task)
    tier = ModelTier(tier_override) if tier_override else classification.tier

    if not daemon_mode:
        console.print(Panel(
            f"[bold]{task}[/bold]\n\n"
            f"Tier: [cyan]{tier.value}[/cyan]  "
            f"Capabilities: [dim]{', '.join(c.value for c in classification.capabilities)}[/dim]\n"
            f"Reason: [dim]{classification.reason}[/dim]",
            title="[bold blue]SilkRoute Agent[/bold blue]",
            border_style="blue",
        ))
    else:
        log.info("agent_started", task=task[:200], tier=tier.value)

    # Step 2: Select model
    model = select_model(tier, classification.capabilities, model_override)
    model_string = get_litellm_model_string(model)

    if not daemon_mode:
        console.print(f"  Model: [bold green]{model.name}[/bold green] ({model_string})")
    else:
        log.info("model_selected", model=model.name, model_string=model_string)

    # Step 3: Initialize session
    session = AgentSession(
        task=task,
        model_id=model.model_id,
        project_id=project_id,
        budget_limit_usd=budget_limit_usd,
    )

    # Budget config needed for both per-session and global checks
    budget_config = BudgetConfig()

    # Step 3b: Database persistence (optional — non-fatal if Postgres unavailable)
    pool = None
    persist = AgentConfig().persist_sessions
    if persist:
        try:
            from silkroute.db.pool import get_pool

            pool = await get_pool()
        except (ImportError, asyncpg.PostgresError, OSError, TimeoutError) as exc:
            log.warning("db_init_skipped", error=str(exc))

    if pool is not None:
        try:
            from silkroute.db.repositories import projects as db_projects
            from silkroute.db.repositories import sessions as db_sessions

            await db_sessions.create_session(pool, session)

            # Check real monthly spend against project budget
            monthly_spend = await db_projects.get_monthly_spend(pool, project_id)
            project_budget = await db_projects.get_project_budget(pool, project_id)
            if project_budget is not None and monthly_spend >= project_budget:
                if not daemon_mode:
                    console.print(
                        f"  [red]Project budget exceeded: "
                        f"${monthly_spend:.2f} / ${project_budget:.2f}[/red]"
                    )
                else:
                    log.warning(
                        "project_budget_exceeded",
                        spend=monthly_spend,
                        budget=project_budget,
                    )
                session.complete(SessionStatus.BUDGET_EXCEEDED)
                await db_sessions.close_session(pool, session)
                return session

            # Global budget enforcement: daily cap, monthly cap, circuit breaker
            daily_spend = await db_projects.get_daily_spend(pool, project_id)
            hourly_rate = await db_projects.get_hourly_spend_rate(pool, project_id)
            global_check = check_global_budget(
                daily_spent=daily_spend,
                monthly_spent=monthly_spend,
                hourly_rate=hourly_rate,
                budget_config=budget_config,
            )
            if not global_check.allowed:
                if not daemon_mode:
                    console.print(f"  [red]{global_check.warning}[/red]")
                else:
                    log.warning("global_budget_exceeded", warning=global_check.warning)
                session.complete(SessionStatus.BUDGET_EXCEEDED)
                await db_sessions.close_session(pool, session)
                return session
            if global_check.warning:
                if not daemon_mode:
                    console.print(f"  [yellow]{global_check.warning}[/yellow]")
                else:
                    log.warning("global_budget_warning", warning=global_check.warning)
        except (asyncpg.PostgresError, OSError, TimeoutError) as exc:
            log.warning("db_session_init_failed", error=str(exc))
            pool = None
        except Exception as exc:
            log.error("db_session_init_unexpected", error=str(exc), exc_info=True)
            pool = None

    pending_db_tasks: list[asyncio.Task[None]] = []

    # Step 4: Set up tools and system prompt (sandbox shell to workspace)
    registry = create_default_registry(workspace_dir=workspace_dir)
    tools = registry.to_openai_tools()

    system_prompt = build_system_prompt(
        project_id=project_id,
        workspace_dir=workspace_dir,
        model_name=model.name,
        budget_remaining=budget_limit_usd,
        max_iterations=max_iterations,
        current_iteration=1,
        task=task,
    )

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    session.messages = messages

    # Configure litellm
    if os.environ.get("SILKROUTE_OPENROUTER_API_KEY"):
        os.environ.setdefault("OPENROUTER_API_KEY", os.environ["SILKROUTE_OPENROUTER_API_KEY"])

    # Suppress litellm's verbose logging
    litellm.suppress_debug_info = True

    if not daemon_mode:
        console.print(
            f"  Budget: [bold]${budget_limit_usd:.2f}[/bold]  "
            f"Max iterations: [bold]{max_iterations}[/bold]\n"
        )

    # Step 5: ReAct loop
    for i in range(1, max_iterations + 1):
        if not daemon_mode:
            console.print(Rule(f"[bold]Iteration {i}[/bold]", style="dim"))

        # Budget check
        budget_check = check_budget(session, model, budget_config)
        if not budget_check.allowed:
            if not daemon_mode:
                console.print(f"  [red]{budget_check.warning}[/red]")
            else:
                log.warning("budget_exceeded", session_id=session.id, warning=budget_check.warning)
            session.complete(SessionStatus.BUDGET_EXCEEDED)
            _push_stream_event(stream_queue, "budget_exceeded", {
                "iteration": i, "warning": budget_check.warning,
            })
            break
        if budget_check.warning:
            if not daemon_mode:
                console.print(f"  [yellow]{budget_check.warning}[/yellow]")
            else:
                log.warning("budget_warning", session_id=session.id, warning=budget_check.warning)

        # Update system prompt with current iteration context
        messages[0]["content"] = build_system_prompt(
            project_id=project_id,
            workspace_dir=workspace_dir,
            model_name=model.name,
            budget_remaining=budget_check.remaining_usd,
            max_iterations=max_iterations,
            current_iteration=i,
            task=task,
        )

        # LLM call
        start_ms = _now_ms()
        try:
            response = await litellm.acompletion(
                model=model_string,
                messages=messages,
                tools=tools,
                tool_choice="auto",
            )
        except Exception as e:
            log.error("llm_call_failed", iteration=i, error=str(e), exc_info=True)
            if not daemon_mode:
                console.print(f"  [red]LLM error: {e}[/red]")
            session.complete(SessionStatus.FAILED)
            _push_stream_event(stream_queue, "error", {
                "iteration": i, "error": str(e),
            })
            break

        latency_ms = _now_ms() - start_ms

        # Track tokens and cost
        input_tokens, output_tokens = _extract_usage(response)
        cost_usd = _extract_cost(response, model, input_tokens, output_tokens)

        choice = response.choices[0]
        assistant_msg = choice.message
        thought = assistant_msg.content or ""

        # Build iteration record
        iteration = Iteration(
            number=i,
            thought=thought,
            cost_usd=cost_usd,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )

        if thought and not daemon_mode:
            trimmed = thought[:200] + ("..." if len(thought) > 200 else "")
            console.print(f"  [dim]Think:[/dim] {trimmed}")

        # Check if task is complete (no tool calls = done)
        tool_calls_raw = assistant_msg.tool_calls
        if not tool_calls_raw:
            session.add_iteration(iteration)
            _schedule_db_writes(pool, pending_db_tasks, session, iteration, model)
            messages.append({"role": "assistant", "content": thought})
            session.complete(SessionStatus.COMPLETED)
            _push_stream_event(stream_queue, "completed", {
                "iteration": i,
                "output": thought[:500],
                "cost_usd": session.total_cost_usd,
            })
            if not daemon_mode:
                console.print("\n  [bold green]Task completed.[/bold green]")
            break

        # Execute tool calls
        # Append the assistant message with tool_calls
        messages.append(assistant_msg.model_dump())

        tool_call_records: list[ToolCall] = []
        for tc in tool_calls_raw[:5]:  # Cap at 5 per iteration
            fn = tc.function
            tool_name = fn.name
            args = parse_tool_arguments(fn.arguments)

            if not daemon_mode:
                console.print(f"  [cyan]Tool:[/cyan] {tool_name}({_truncate_args(args)})")

            tc_start = _now_ms()
            result = await registry.execute(tool_name, args)
            tc_duration = _now_ms() - tc_start

            success = not result.startswith("Error")
            if not daemon_mode:
                style = "green" if success else "red"
                trimmed_result = result[:150] + ("..." if len(result) > 150 else "")
                console.print(f"    [{style}]→ {trimmed_result}[/{style}]")

            tool_call_records.append(ToolCall(
                tool_name=tool_name,
                tool_input=args,
                tool_output=result,
                success=success,
                error_message=result if not success else "",
                duration_ms=tc_duration,
            ))

            # Append tool result message
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

        iteration.tool_calls = tool_call_records
        session.add_iteration(iteration)
        _schedule_db_writes(pool, pending_db_tasks, session, iteration, model)

        _push_stream_event(stream_queue, "iteration", {
            "iteration": i,
            "tools_called": len(tool_call_records),
            "cost_usd": cost_usd,
            "thought": thought[:200],
        })

        log.info(
            "iteration_complete",
            iteration=i,
            tools_called=len(tool_call_records),
            cost_usd=cost_usd,
            latency_ms=latency_ms,
        )
    else:
        # Loop exhausted without completion
        session.complete(SessionStatus.TIMEOUT)
        if not daemon_mode:
            console.print(f"\n  [yellow]Max iterations ({max_iterations}) reached.[/yellow]")

    # Flush pending DB writes and close session
    if pending_db_tasks:
        await asyncio.gather(*pending_db_tasks, return_exceptions=True)
    if pool is not None:
        try:
            from silkroute.db.repositories import sessions as db_sessions

            await db_sessions.close_session(pool, session)
        except (asyncpg.PostgresError, OSError) as exc:
            log.warning("db_session_close_failed", error=str(exc))

    # Signal stream end
    if stream_queue is not None:
        await stream_queue.put(None)

    # Summary
    if not daemon_mode:
        console.print()
        console.print(Panel(
            f"Status: [bold]{session.status.value}[/bold]\n"
            f"Iterations: {session.iteration_count}\n"
            f"Total cost: [green]${session.total_cost_usd:.4f}[/green]\n"
            f"Tokens: {session.total_input_tokens:,} in / {session.total_output_tokens:,} out",
            title="[bold]Session Summary[/bold]",
            border_style="green" if session.status == SessionStatus.COMPLETED else "yellow",
        ))
    else:
        log.info(
            "agent_completed",
            session_id=session.id,
            status=session.status.value,
            iterations=session.iteration_count,
            cost_usd=session.total_cost_usd,
        )

    return session


def _extract_usage(response: object) -> tuple[int, int]:
    """Extract token counts from litellm response."""
    usage = getattr(response, "usage", None)
    if usage:
        return (
            getattr(usage, "prompt_tokens", 0) or 0,
            getattr(usage, "completion_tokens", 0) or 0,
        )
    return (0, 0)


def _extract_cost(
    response: object,
    model: ModelSpec,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Extract cost with triple fallback: litellm → hidden_params → estimate_cost."""

    # Fallback 1: litellm completion_cost
    try:
        cost = litellm.completion_cost(completion_response=response)
        if cost and cost > 0:
            return cost
    except Exception:
        pass

    # Fallback 2: _hidden_params
    try:
        hidden = getattr(response, "_hidden_params", {})
        cost = hidden.get("response_cost")
        if cost and cost > 0:
            return cost
    except Exception:
        pass

    # Fallback 3: Our own estimate
    return estimate_cost(model, input_tokens, output_tokens)


def _push_stream_event(
    queue: asyncio.Queue[str | None] | None,
    event_type: str,
    data: dict[str, Any],
) -> None:
    """Push a JSON stream event to the queue if it's active.

    Non-blocking: uses put_nowait so the agent loop is never
    stalled by a slow consumer.
    """
    if queue is None:
        return
    payload = json.dumps({"type": event_type, **data})
    try:
        queue.put_nowait(payload)
    except asyncio.QueueFull:
        log.warning("stream_queue_full", event_type=event_type)


def _now_ms() -> int:
    """Current time in milliseconds."""
    return int(time.monotonic() * 1000)


def _truncate_args(args: dict) -> str:
    """Format args dict for display, truncating long values."""
    parts = []
    for k, v in args.items():
        sv = str(v)
        if len(sv) > 60:
            sv = sv[:60] + "..."
        parts.append(f"{k}={sv!r}")
    return ", ".join(parts)


def _schedule_db_writes(
    pool: object | None,
    pending: list[asyncio.Task[None]],
    session: AgentSession,
    iteration: Iteration,
    model: ModelSpec,
) -> None:
    """Fire-and-forget DB writes for the current iteration.

    Appends tasks to *pending* so they can be awaited before returning.
    Includes session update, cost log, and tool audit log.
    """
    if pool is None:
        return
    try:
        from silkroute.db.repositories import cost_logs as db_cost_logs
        from silkroute.db.repositories import sessions as db_sessions
        from silkroute.db.repositories import tool_audit as db_tool_audit

        pending.append(asyncio.create_task(db_sessions.update_session(pool, session)))
        pending.append(asyncio.create_task(
            db_cost_logs.insert_cost_log(pool, session, iteration, model),
        ))
        if iteration.tool_calls:
            pending.append(asyncio.create_task(
                db_tool_audit.insert_tool_audit_logs(pool, session, iteration),
            ))
    except Exception as exc:
        log.warning("db_write_schedule_failed", error=str(exc))
