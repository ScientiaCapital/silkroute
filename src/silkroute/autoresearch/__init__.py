"""AutoResearch — autonomous experiment engine for SilkRoute.

Inspired by Karpathy's autoresearch: modify code, run eval, keep or discard,
loop forever. Uses Chinese LLMs as the researcher via OpenRouter.
"""

from silkroute.autoresearch.engine import ResearchEngine
from silkroute.autoresearch.metrics import Metrics

__all__ = ["Metrics", "ResearchEngine"]
