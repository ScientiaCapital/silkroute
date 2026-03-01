"""LLM-powered task decomposition using OpenRouter.

Uses a free-tier model (deepseek/deepseek-r1-0528:free) to intelligently
decompose compound tasks. Falls back to KeywordDecomposer on any error,
including when called from an async context (synchronous wrapper limitation).

Cache: LRU (OrderedDict), keyed by SHA-256 prefix of the task string.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import OrderedDict
from typing import Any

import structlog

from silkroute.agent.classifier import classify_task
from silkroute.mantis.orchestrator.decomposer import KeywordDecomposer
from silkroute.mantis.orchestrator.models import OrchestrationPlan, SubTask
from silkroute.mantis.runtime.interface import RuntimeConfig

log = structlog.get_logger()

_DECOMPOSE_SYSTEM_PROMPT = (
    "You are a task decomposition engine. Given a task description, "
    "break it into independent sub-tasks.\n\n"
    "Output ONLY valid JSON:\n"
    '{"sub_tasks": [{"description": "...", "tier_hint": "free|standard|premium",'
    ' "depends_on": []}]}\n\n'
    "Rules:\n"
    "- Each sub-task should be independently executable\n"
    "- Use depends_on (list of 0-indexed integers) for sequential dependencies\n"
    "- tier_hint: 'free' for simple/boilerplate, 'standard' for moderate complexity,"
    " 'premium' for reasoning/analysis\n"
    "- Maximum 5 sub-tasks\n"
    "- If the task is simple and doesn't need decomposition, return a single sub-task"
)


class LLMDecomposer:
    """LLM-powered task decomposer with caching and fallback.

    Uses deepseek/deepseek-r1-0528:free via OpenRouter for intelligent
    decomposition. Falls back to KeywordDecomposer on any error.

    Args:
        model_id: OpenRouter model identifier for decomposition.
        llm_factory: Optional callable that creates an LLM given a model_id.
            If None, uses create_openrouter_model from providers.openrouter.
        cache_maxsize: Maximum number of cached decomposition results.
    """

    def __init__(
        self,
        model_id: str = "deepseek/deepseek-r1-0528:free",
        llm_factory: Any | None = None,  # noqa: ANN401
        cache_maxsize: int = 100,
    ) -> None:
        self._model_id = model_id
        self._llm_factory = llm_factory
        self._cache: OrderedDict[str, OrchestrationPlan] = OrderedDict()
        self._cache_maxsize = cache_maxsize
        self._fallback = KeywordDecomposer()

    def decompose(self, task: str, config: RuntimeConfig | None = None) -> OrchestrationPlan:
        """Decompose task using LLM. Falls back to keyword decomposer on error.

        Cache hit: returns cached plan immediately (LRU order updated).
        Cache miss: calls LLM synchronously, stores result.
        Error: logs warning and falls back to KeywordDecomposer.
        """
        # Check cache first
        cache_key = self._cache_key(task)
        if cache_key in self._cache:
            self._cache.move_to_end(cache_key)
            return self._cache[cache_key]

        # Try LLM decomposition
        try:
            plan = self._llm_decompose(task, config)
            self._cache_put(cache_key, plan)
            return plan
        except Exception as exc:
            log.warning("llm_decomposer_fallback", error=str(exc), task=task[:100])
            return self._fallback.decompose(task, config)

    def _llm_decompose(self, task: str, config: RuntimeConfig | None = None) -> OrchestrationPlan:
        """Synchronous wrapper around async LLM call.

        Raises RuntimeError if called from within a running event loop
        (e.g., inside an async context), to trigger the fallback path.
        """
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Cannot call asyncio.run() from within a running loop
            raise RuntimeError("Cannot call LLM synchronously from async context")

        return asyncio.run(self._async_llm_decompose(task, config))

    async def _async_llm_decompose(
        self, task: str, config: RuntimeConfig | None = None
    ) -> OrchestrationPlan:
        """Async LLM decomposition via OpenRouter."""
        cfg = config or RuntimeConfig()

        if self._llm_factory is None:
            from silkroute.providers.openrouter import create_openrouter_model

            llm = create_openrouter_model(model_id=self._model_id)
        else:
            llm = self._llm_factory(self._model_id)

        from langchain_core.messages import HumanMessage, SystemMessage

        response = await llm.ainvoke([
            SystemMessage(content=_DECOMPOSE_SYSTEM_PROMPT),
            HumanMessage(content=f"Decompose this task:\n{task}"),
        ])

        return self._parse_response(response.content, task, cfg)

    def _parse_response(
        self, content: str, task: str, config: RuntimeConfig
    ) -> OrchestrationPlan:
        """Parse LLM JSON response into an OrchestrationPlan.

        Handles markdown-fenced JSON (```json...```) and bare JSON objects.

        Raises:
            ValueError: If no valid JSON or empty sub_tasks in response.
        """
        # Strip markdown fences if present
        json_match = re.search(r"\{[\s\S]*\}", content)
        if not json_match:
            raise ValueError(f"No JSON found in LLM response: {content[:200]!r}")

        data = json.loads(json_match.group())
        raw_tasks = data.get("sub_tasks", [])

        if not raw_tasks:
            raise ValueError("Empty sub_tasks in LLM response")

        # Build sub-tasks, capped at 5
        sub_tasks: list[SubTask] = []
        id_map: dict[int, str] = {}

        for i, raw in enumerate(raw_tasks[:5]):
            description = raw.get("description", "")
            classification = classify_task(description)
            tier = raw.get("tier_hint", classification.tier.value)

            st = SubTask(
                parent_task=task,
                description=description,
                runtime_type=config.runtime_type,
                tier_hint=tier,
                max_iterations=config.max_iterations,
                priority=len(raw_tasks) - i,
            )
            id_map[i] = st.id

            # Map depends_on indices to actual sub-task IDs
            deps = raw.get("depends_on", [])
            st.depends_on = [id_map[d] for d in deps if d in id_map]

            sub_tasks.append(st)

        strategy = "parallel_stages" if len(sub_tasks) > 1 else "single"
        return OrchestrationPlan(
            parent_task=task,
            sub_tasks=sub_tasks,
            strategy=strategy,
            total_budget_usd=config.budget_limit_usd,
        )

    def _cache_key(self, task: str) -> str:
        """16-char SHA-256 prefix as cache key."""
        return hashlib.sha256(task.encode()).hexdigest()[:16]

    def _cache_put(self, key: str, plan: OrchestrationPlan) -> None:
        """Insert plan into LRU cache, evicting oldest if over capacity."""
        self._cache[key] = plan
        if len(self._cache) > self._cache_maxsize:
            self._cache.popitem(last=False)  # Remove least-recently-used (first inserted)
