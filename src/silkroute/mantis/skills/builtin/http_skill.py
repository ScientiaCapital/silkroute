"""HTTP request skill with SSRF protection.

Provides agents with the ability to make outbound HTTP requests while
blocking RFC 1918 private addresses, loopback, and link-local ranges.
"""

from __future__ import annotations

import httpx
import structlog

from silkroute.mantis.skills.models import SkillCategory, SkillContext, SkillSpec
from silkroute.network.ssrf import is_ssrf_blocked as _is_blocked_url

log = structlog.get_logger()

_MAX_RESPONSE_BYTES = 20 * 1024  # 20 KB


async def _http_request_handler(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: str = "",
    timeout: int = 30,
    _skill_ctx: SkillContext | None = None,
) -> str:
    """Make an HTTP request with SSRF protection."""
    # Clamp timeout
    timeout = min(max(timeout, 1), 60)

    # SSRF check
    block_reason = _is_blocked_url(url)
    if block_reason is not None:
        return f"Error: {block_reason}"

    method = method.upper()
    allowed_methods = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"}
    if method not in allowed_methods:
        allowed = ", ".join(sorted(allowed_methods))
        return f"Error: Method '{method}' not allowed. Use one of: {allowed}"

    req_headers = headers or {}

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=req_headers,
                content=body.encode() if body else None,
            )

        raw = response.content[:_MAX_RESPONSE_BYTES]
        truncated = len(response.content) > _MAX_RESPONSE_BYTES
        text = raw.decode(errors="replace")

        result = f"HTTP {response.status_code} {response.reason_phrase}\n"
        result += f"Content-Type: {response.headers.get('content-type', 'unknown')}\n\n"
        result += text
        if truncated:
            result += f"\n\n[Truncated: response exceeded {_MAX_RESPONSE_BYTES} bytes]"

        return result
    except httpx.TimeoutException:
        return f"Error: Request timed out after {timeout}s"
    except httpx.RequestError as e:
        log.warning("http_skill_request_error", error=str(e))
        return f"Error making HTTP request: {e}"
    except Exception as e:
        log.error("http_skill_unexpected_error", error=str(e), exc_info=True)
        return f"Error making HTTP request: {e}"


http_request_skill = SkillSpec(
    name="http_request",
    description=(
        "Make an outbound HTTP request to a URL. "
        "Blocked: private IPs (10.x, 172.16-31.x, 192.168.x), loopback (127.x), "
        "link-local (169.254.x), file:// and other non-http schemes. "
        "Response truncated at 20 KB."
    ),
    category=SkillCategory.WEB,
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to request (must be http or https)",
            },
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"],
                "description": "HTTP method (default: GET)",
                "default": "GET",
            },
            "headers": {
                "type": "object",
                "description": "Optional HTTP headers as key-value pairs",
                "default": {},
            },
            "body": {
                "type": "string",
                "description": "Optional request body (for POST/PUT/PATCH)",
                "default": "",
            },
            "timeout": {
                "type": "integer",
                "description": "Request timeout in seconds (1-60, default: 30)",
                "default": 30,
            },
        },
        "required": ["url"],
    },
    handler=_http_request_handler,
    required_tools=[],
)
