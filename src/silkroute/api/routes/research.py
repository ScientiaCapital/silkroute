"""AutoResearch ledger endpoint — inspect experiment history.

GET /research/ledger → recent experiment results + keep/discard/crash counts + best score

The Ledger is TSV-backed, local-disk file I/O (see autoresearch/ledger.py) — there's
no database involved, so this fails open the same way /memories does when Postgres
is unreachable: a missing ledger file means "no experiments have run yet", not an error.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, Query

from silkroute.api.auth import require_auth
from silkroute.api.models import LedgerEntryResponse, LedgerSummaryResponse
from silkroute.autoresearch.ledger import Ledger, LedgerEntry

router = APIRouter(prefix="/research", tags=["research"], dependencies=[Depends(require_auth)])


def _entry_to_response(entry: LedgerEntry) -> LedgerEntryResponse:
    return LedgerEntryResponse(
        commit=entry.commit,
        score=entry.score,
        pass_rate=entry.pass_rate,
        coverage=entry.coverage,
        status=entry.status,
        description=entry.description,
    )


@router.get("/ledger")
async def get_ledger(
    limit: int = Query(default=50, le=200),
) -> LedgerSummaryResponse:
    """Return recent autoresearch experiments, status counts, and the best kept score."""
    ledger = Ledger(Path.cwd() / ".silkroute" / "autoresearch" / "results.tsv")

    if not ledger.path.exists():
        return LedgerSummaryResponse(entries=[], counts={}, best=None, available=False)

    entries, counts, best = await asyncio.to_thread(
        lambda: (ledger.recent(limit), ledger.count(), ledger.best()),
    )
    return LedgerSummaryResponse(
        entries=[_entry_to_response(e) for e in entries],
        counts=counts,
        best=_entry_to_response(best) if best else None,
    )
