"""Bearer token authentication for the SilkRoute API.

Uses secrets.compare_digest() for timing-safe comparison.
When SILKROUTE_API_KEY is empty (default), auth is disabled (dev mode).
"""

from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from silkroute.api.deps import get_api_config
from silkroute.config.settings import ApiConfig

_bearer_scheme = HTTPBearer(auto_error=False)


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    api_config: ApiConfig = Depends(get_api_config),
) -> None:
    """Verify bearer token if API key is configured.

    - Empty SILKROUTE_API_KEY → auth disabled (dev mode)
    - Missing/invalid token → 401
    """
    expected = api_config.api_key
    if not expected:
        return  # Dev mode: no auth required

    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not secrets.compare_digest(credentials.credentials, expected):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
