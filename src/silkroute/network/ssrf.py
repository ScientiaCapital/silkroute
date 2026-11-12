"""Unified SSRF protection for SilkRoute.

Policy (fail-closed):

- Only ``http`` and ``https`` schemes are allowed.
- ``localhost`` / ``*.localhost`` (with or without a trailing dot) are blocked.
- Numeric IPv4 spellings that ``inet_aton`` accepts (decimal ``2130706433``,
  hex ``0x7f000001``, octal ``0177.0.0.1``, short ``127.1``) are decoded and
  checked like any other literal.
- Every address is checked after unmapping IPv4-mapped (``::ffff:a.b.c.d``)
  and 6to4 (``2002::/16``) IPv6 addresses to their embedded IPv4 address.
- An address is allowed only if ``ip.is_global`` is true and it is not
  reserved, multicast, loopback, link-local, private or unspecified. This
  blocks ``0.0.0.0``, ``::``, RFC 1918, CGNAT ``100.64.0.0/10`` (which covers
  ``100.100.100.200``, the Alibaba Cloud metadata IP), ``169.254.169.254``,
  ULA, link-local and similar ranges.
- Hostnames are resolved with ``socket.getaddrinfo`` and EVERY returned
  address must pass. Resolution errors or an empty result block the request.

:class:`SSRFPinnedTransport` re-runs the check at connection time and pins
the TCP connection to the address it just checked (keeping the original Host
header and TLS SNI / certificate hostname), so a DNS answer that changes
between the check and the connect (DNS rebinding) cannot redirect the
connection to an internal address. :func:`guarded_request` disables
automatic redirects and follows them manually, re-checking every hop.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

MAX_REDIRECTS = 5
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

# Module-level alias so tests can stub resolution without patching the
# process-wide ``socket`` module.
_getaddrinfo = socket.getaddrinfo


class SSRFBlockedError(httpx.RequestError):
    """Raised when a request (or a redirect hop) targets a blocked address."""


def is_ssrf_blocked(url: str) -> str | None:
    """Return a reason string if ``url`` must be SSRF-blocked, else ``None``."""
    reason, _ = check_url(url)
    return reason


def check_url(url: str) -> tuple[str | None, list[IPAddress]]:
    """Validate ``url`` and return ``(reason, checked_addresses)``.

    ``reason`` is ``None`` when the URL is allowed; ``checked_addresses`` then
    holds every address the host resolved to (all of them passed the check).
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        port = parsed.port
    except ValueError as exc:
        return f"Blocked: unparseable URL ({exc})", []

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        if scheme == "file":
            return "Blocked: file:// scheme is not allowed", []
        return f"Blocked: scheme '{parsed.scheme}' is not allowed (only http/https)", []

    host = hostname.lower().rstrip(".")
    if host in ("localhost", "") or host.endswith(".localhost"):
        return f"Blocked: loopback hostname '{hostname}' is not allowed", []

    literal = _parse_literal(hostname)
    if literal is not None:
        reason = _check_ip(literal, hostname)
        return reason, ([] if reason else [literal])

    try:
        infos = _getaddrinfo(hostname, port or None, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError, ValueError) as exc:
        return f"Blocked: could not resolve '{hostname}' ({exc}); failing closed", []

    addrs: list[IPAddress] = []
    for info in infos:
        raw = str(info[4][0]).split("%", 1)[0]
        try:
            addr = ipaddress.ip_address(raw)
        except ValueError:
            return f"Blocked: '{hostname}' resolved to unparseable address {raw!r}", []
        reason = _check_ip(addr, f"'{hostname}' resolves to {addr}")
        if reason is not None:
            return reason, []
        if addr not in addrs:
            addrs.append(addr)

    if not addrs:
        return f"Blocked: '{hostname}' resolved to no addresses; failing closed", []
    return None, addrs


def _parse_literal(hostname: str) -> IPAddress | None:
    """Parse ``hostname`` as an IP literal, including legacy IPv4 spellings."""
    try:
        return ipaddress.ip_address(hostname)
    except ValueError:
        pass
    # inet_aton accepts decimal/hex/octal/short forms that OS resolvers also
    # accept (e.g. "2130706433" == 127.0.0.1). It is a pure parser, no DNS.
    try:
        return ipaddress.IPv4Address(socket.inet_aton(hostname))
    except (OSError, ValueError, UnicodeError):
        return None


def _unmap(addr: IPAddress) -> IPAddress:
    """Return the embedded IPv4 address for IPv4-mapped / 6to4 IPv6 addresses."""
    if isinstance(addr, ipaddress.IPv6Address):
        if addr.ipv4_mapped is not None:
            return addr.ipv4_mapped
        if addr.sixtofour is not None:
            return addr.sixtofour
    return addr


def _check_ip(addr: IPAddress, label: str) -> str | None:
    """Block anything that is not a globally routable unicast address."""
    candidates = [addr]
    unmapped = _unmap(addr)
    if unmapped != addr:
        candidates.append(unmapped)
    for candidate in candidates:
        if (
            not candidate.is_global
            or candidate.is_reserved
            or candidate.is_multicast
            or candidate.is_loopback
            or candidate.is_link_local
            or candidate.is_private
            or candidate.is_unspecified
        ):
            kind = _classify_ip(candidate)
            return f"Blocked: {kind} address {label} is not a public address"
    return None


def _classify_ip(addr: IPAddress) -> str:
    """Return a human-readable classification for a blocked IP."""
    if addr.is_unspecified:
        return "unspecified"
    if addr.is_loopback:
        return "loopback"
    if addr.is_link_local:
        return "link-local"
    if addr.is_multicast:
        return "multicast"
    if addr.is_private:
        return "private/RFC-1918"
    return "reserved/non-global"


class SSRFPinnedTransport(httpx.AsyncBaseTransport):
    """httpx transport that re-checks the target and pins the connection.

    For each request it resolves and checks the host (all addresses must be
    public), then rewrites the request URL to the first checked IP. The Host
    header is left as the original hostname and the TLS SNI / certificate
    hostname is set via the ``sni_hostname`` request extension, so virtual
    hosting and certificate verification still use the real name.

    Passing a custom transport disables httpx's environment proxy support, so
    requests never go through an HTTP(S)_PROXY that would bypass the pin.
    """

    def __init__(self, inner: httpx.AsyncBaseTransport | None = None) -> None:
        self._inner = inner if inner is not None else httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        reason, addrs = check_url(str(request.url))
        if reason is not None:
            raise SSRFBlockedError(reason, request=request)
        original_host = request.url.host
        extensions = dict(request.extensions)
        if request.url.scheme == "https":
            extensions.setdefault("sni_hostname", original_host)
        request.url = request.url.copy_with(host=str(addrs[0]))
        request.extensions = extensions
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()


async def guarded_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    content: bytes | None = None,
    timeout: float | None = None,
    max_redirects: int = MAX_REDIRECTS,
) -> httpx.Response:
    """Send a request, following up to ``max_redirects`` redirects manually.

    The client must be created with ``follow_redirects=False``. Every hop's
    target is SSRF-checked before it is requested; a blocked hop raises
    :class:`SSRFBlockedError`. Too many hops raises ``httpx.TooManyRedirects``.
    """
    current_url = url
    current_method = method.upper()
    current_headers = dict(headers or {})
    current_content = content

    for _hop in range(max_redirects + 1):
        reason = is_ssrf_blocked(current_url)
        if reason is not None:
            raise SSRFBlockedError(reason)

        kwargs: dict[str, object] = {
            "method": current_method,
            "url": current_url,
            "headers": current_headers,
            "content": current_content,
        }
        if timeout is not None:
            kwargs["timeout"] = timeout
        response = await client.request(**kwargs)  # type: ignore[arg-type]

        location = None
        if response.status_code in _REDIRECT_STATUSES:
            location = response.headers.get("location")
        if not location:
            return response

        next_url = urljoin(current_url, location)
        # Same method rewriting as browsers / httpx.
        status = response.status_code
        see_other = status == 303 and current_method != "HEAD"
        post_moved = status in (301, 302) and current_method == "POST"
        if see_other or post_moved:
            current_method, current_content = "GET", None
        # Never forward credentials to a different origin.
        if urlparse(next_url)[:2] != urlparse(current_url)[:2]:
            current_headers = {
                k: v
                for k, v in current_headers.items()
                if k.lower() not in ("authorization", "cookie", "proxy-authorization")
            }
        current_url = next_url

    raise httpx.TooManyRedirects(f"Exceeded maximum of {max_redirects} redirects")
