"""Context7 documentation API routes."""

from __future__ import annotations

import structlog
from fastapi import APIRouter

from silkroute.api.models import (
    Context7QueryRequest,
    Context7QueryResponse,
    Context7ResolveRequest,
    Context7ResolveResponse,
)
from silkroute.mantis.skills.context7 import Context7Client

log = structlog.get_logger()
router = APIRouter(prefix="/context7", tags=["context7"])


def _get_client() -> Context7Client:
    """Get a Context7 client with default settings."""
    from silkroute.config.settings import Context7Config

    cfg = Context7Config()
    return Context7Client(
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        timeout=cfg.timeout_seconds,
        max_snippets=cfg.max_snippets,
        max_context_tokens=cfg.max_context_tokens,
        max_concurrent=cfg.max_concurrent_requests,
    )


@router.post("/resolve", response_model=Context7ResolveResponse)
async def resolve_library(req: Context7ResolveRequest) -> Context7ResolveResponse:
    """Resolve a library name to a Context7 library ID."""
    client = _get_client()
    try:
        lib = await client.resolve_library(req.library_name, req.query)
        if lib is None:
            return Context7ResolveResponse(found=False)
        return Context7ResolveResponse(
            found=True,
            library_id=lib.id,
            library_name=lib.name,
            version=lib.version,
            trust_score=lib.trust_score,
        )
    except Exception as exc:
        log.warning("context7_resolve_error", error=str(exc))
        return Context7ResolveResponse(found=False)


@router.post("/query", response_model=Context7QueryResponse)
async def query_docs(req: Context7QueryRequest) -> Context7QueryResponse:
    """Query Context7 for library documentation."""
    client = _get_client()
    try:
        result = await client.query(req.library_name, req.query)
        return Context7QueryResponse(
            library_name=req.library_name,
            snippets=[
                {
                    "title": s.title,
                    "content": s.content,
                    "url": s.url,
                    "relevance": s.relevance,
                }
                for s in result.snippets
            ],
            truncated=result.truncated,
        )
    except Exception as exc:
        log.warning("context7_query_error", error=str(exc))
        return Context7QueryResponse(
            library_name=req.library_name,
            error=str(exc),
        )
