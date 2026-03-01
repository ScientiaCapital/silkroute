"""HTTP request skill with SSRF protection.

Provides agents with the ability to make outbound HTTP requests while
blocking RFC 1918 private addresses, loopback, and link-local ranges.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx
import structlog

from silkroute.mantis.skills.models import SkillCategory, SkillContext, SkillSpec

log = structlog.get_logger()

_MAX_RESPONSE_BYTES = 20 * 1024  # 20 KB

# Blocked hostname patterns (literal matches)
_BLOCKED_HOSTNAMES = frozenset(["localhost"])

# Private/reserved IP network ranges (SSRF protection)
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_blocked_url(url: str) -> str | None:
    """Check if a URL should be blocked for SSRF reasons.

    Returns an error message string if blocked, None if safe.
    """
    parsed = urlparse(url)

    # Block non-http(s) schemes
    if parsed.scheme.lower() not in ("http", "https"):
        return f"Blocked: scheme '{parsed.scheme}' is not permitted (only http/https)"

    hostname = parsed.hostname or ""

    # Block localhost by name
    if hostname.lower() in _BLOCKED_HOSTNAMES:
        return f"Blocked: hostname '{hostname}' is reserved"

    # Block by IP address range
    try:
        addr = ipaddress.ip_address(hostname)
        for network in _BLOCKED_NETWORKS:
            if addr in network:
                return f"Blocked: IP {hostname} is in a private/reserved range"
    except ValueError:
        # Not a bare IP — resolve to check
        try:
            resolved_ip = socket.gethostbyname(hostname)
            addr = ipaddress.ip_address(resolved_ip)
            for network in _BLOCKED_NETWORKS:
                if addr in network:
                    return f"Blocked: '{hostname}' resolves to private/reserved IP {resolved_ip}"
        except (OSError, ValueError):
            # DNS failure or invalid hostname — allow through (fail-open on DNS errors)
            pass

    return None


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
    except Exception as e:
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
