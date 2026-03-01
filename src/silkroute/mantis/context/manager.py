"""ContextManager — versioned, token-aware, scope-filtered context store.

Provides inter-step context sharing for supervisor plans. Thread-safe via
asyncio.Lock. Supports checkpoint serialization for persistence.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from silkroute.mantis.context.models import ContextEntry, ContextScope, ContextSnapshot

log = structlog.get_logger()

_LEGACY_META_KEY = "__silkroute_context_meta__"


class ContextManager:
    """Versioned, token-aware context store for agent plan execution.

    Stores entries by key with scope (STEP/PLAN/SESSION) and source tracking.
    On token overflow, evicts oldest STEP-scoped entries.

    Thread-safe: all writes use asyncio.Lock (same pattern as BudgetTracker).
    """

    def __init__(self, max_tokens: int = 8000) -> None:
        self._max_tokens = max_tokens
        self._entries: dict[str, ContextEntry] = {}
        self._total_tokens: int = 0
        self._lock = asyncio.Lock()
        self._snapshot_version: int = 1

    async def set(
        self,
        key: str,
        value: object,
        scope: ContextScope,
        source: str = "",
        token_estimate: int = 0,
    ) -> None:
        """Store or update a context entry.

        Increments version on update. Evicts STEP-scoped entries on overflow.
        """
        async with self._lock:
            existing = self._entries.get(key)

            if existing is not None:
                # Update: remove old token count, bump version
                self._total_tokens -= existing.token_estimate
                new_version = existing.version + 1
            else:
                new_version = 1

            entry = ContextEntry(
                key=key,
                value=value,
                scope=scope,
                source=source,
                token_estimate=token_estimate,
                version=new_version,
            )
            self._entries[key] = entry
            self._total_tokens += token_estimate

            # Evict STEP-scoped entries if over budget
            if self._total_tokens > self._max_tokens:
                self._evict_step_entries()

    def _evict_step_entries(self) -> None:
        """Evict STEP-scoped entries (oldest first) until under token budget.

        Called with _lock held.
        """
        step_keys = [
            k for k, v in self._entries.items()
            if v.scope == ContextScope.STEP
        ]
        # Evict by insertion order (dict preserves order in Python 3.7+)
        for key in step_keys:
            if self._total_tokens <= self._max_tokens:
                break
            entry = self._entries.pop(key)
            self._total_tokens -= entry.token_estimate
            log.debug("context_evicted", key=key, tokens=entry.token_estimate)

    def get(self, key: str) -> ContextEntry | None:
        """Look up a context entry by key."""
        return self._entries.get(key)

    def get_for_step(self, step_id: str) -> dict[str, Any]:
        """Return context relevant to a specific step.

        Includes:
        - All PLAN and SESSION scoped entries (global context)
        - STEP scoped entries where source == step_id
        """
        result: dict[str, Any] = {}
        for key, entry in self._entries.items():
            if entry.scope in (ContextScope.PLAN, ContextScope.SESSION) or (
                entry.scope == ContextScope.STEP and entry.source == step_id
            ):
                result[key] = entry.value
        return result

    def snapshot(self) -> ContextSnapshot:
        """Create a serializable snapshot for checkpoint persistence."""
        return ContextSnapshot(
            entries=dict(self._entries),
            total_tokens=self._total_tokens,
            version=self._snapshot_version,
        )

    def restore(self, snapshot: ContextSnapshot) -> None:
        """Restore state from a checkpoint snapshot."""
        self._entries = dict(snapshot.entries)
        self._total_tokens = snapshot.total_tokens
        self._snapshot_version = snapshot.version
        log.debug("context_restored", entries=len(self._entries), tokens=self._total_tokens)

    def to_legacy_dict(self) -> dict[str, Any]:
        """Return backward-compat dict for supervisor plan.context.

        Includes raw values plus a __silkroute_context_meta__ key for metadata.
        """
        result: dict[str, Any] = {}
        meta: dict[str, Any] = {}

        for key, entry in self._entries.items():
            result[key] = entry.value
            meta[key] = {
                "scope": entry.scope,
                "source": entry.source,
                "token_estimate": entry.token_estimate,
                "version": entry.version,
            }

        result[_LEGACY_META_KEY] = meta
        return result

    @classmethod
    def from_legacy_dict(cls, data: dict[str, Any], max_tokens: int = 8000) -> ContextManager:
        """Restore a ContextManager from a legacy plan.context dict.

        Handles both plain dicts (no metadata) and dicts with
        __silkroute_context_meta__ from to_legacy_dict().
        """
        manager = cls(max_tokens=max_tokens)
        meta = data.get(_LEGACY_META_KEY, {})

        for key, value in data.items():
            if key == _LEGACY_META_KEY:
                continue

            entry_meta = meta.get(key, {})
            scope_raw = entry_meta.get("scope", ContextScope.PLAN)
            try:
                scope = ContextScope(scope_raw)
            except ValueError:
                scope = ContextScope.PLAN

            entry = ContextEntry(
                key=key,
                value=value,
                scope=scope,
                source=entry_meta.get("source", ""),
                token_estimate=entry_meta.get("token_estimate", 0),
                version=entry_meta.get("version", 1),
            )
            manager._entries[key] = entry
            manager._total_tokens += entry.token_estimate

        return manager
