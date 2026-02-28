"""Model catalog endpoints — list and detail.

GET /models            → Full catalog (filterable by tier, capability)
GET /models/{model_id} → Single model detail
"""

from __future__ import annotations

from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query

from silkroute.api.models import ModelResponse
from silkroute.config.settings import ModelTier
from silkroute.providers.models import ALL_MODELS, MODELS_BY_TIER, ModelSpec

router = APIRouter(prefix="/models", tags=["models"])


def _model_to_response(spec: ModelSpec) -> ModelResponse:
    return ModelResponse(
        model_id=spec.model_id,
        name=spec.name,
        provider=spec.provider.value,
        tier=spec.tier.value,
        input_cost_per_m=spec.input_cost_per_m,
        output_cost_per_m=spec.output_cost_per_m,
        context_window=spec.context_window,
        max_output_tokens=spec.max_output_tokens,
        capabilities=[c.value for c in spec.capabilities],
        supports_tool_calling=spec.supports_tool_calling,
        supports_streaming=spec.supports_streaming,
        is_moe=spec.is_moe,
        is_free=spec.is_free,
    )


@router.get("")
async def list_models(
    tier: str | None = Query(default=None, description="Filter by tier: free, standard, premium"),
    capability: str | None = Query(default=None, description="Filter by capability"),
) -> list[ModelResponse]:
    """List all models in the catalog, optionally filtered."""
    if tier is not None:
        try:
            tier_enum = ModelTier(tier)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid tier: {tier}. Must be one of: free, standard, premium",
            ) from exc
        candidates = MODELS_BY_TIER.get(tier_enum, [])
    else:
        candidates = list(ALL_MODELS.values())

    if capability is not None:
        candidates = [
            m for m in candidates
            if capability in [c.value for c in m.capabilities]
        ]

    return [_model_to_response(m) for m in candidates]


@router.get("/{model_id:path}")
async def get_model_detail(model_id: str) -> ModelResponse:
    """Get details for a specific model.

    model_id is URL-encoded (e.g., deepseek%2Fdeepseek-v3.2).
    """
    decoded = unquote(model_id)
    spec = ALL_MODELS.get(decoded)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Model not found: {decoded}")
    return _model_to_response(spec)
