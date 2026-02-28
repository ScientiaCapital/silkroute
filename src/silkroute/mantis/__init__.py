"""Mantis — multi-agent orchestration layer for SilkRoute.

This package evolves SilkRoute from a single-agent ReAct loop into
a multi-agent autonomous system. The migration follows a strangler fig
pattern: new Mantis code wraps existing SilkRoute components, then
gradually replaces internals.

Phase 0: Runtime abstraction layer (interface + legacy wrapper)
Phase 1+: OpenRouter adapter, Deep Agents, orchestrator, supervisor
"""
