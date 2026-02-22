"""SilkRoute database layer — asyncpg persistence for sessions, costs, and budgets.

All database operations are non-fatal: the agent continues running even if
PostgreSQL is unavailable. Persistence is an observability feature, not a
hard dependency.
"""

from silkroute.db.pool import close_pool, get_pool

__all__ = ["get_pool", "close_pool"]
