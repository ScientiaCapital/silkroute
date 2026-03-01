"""Unified SSRF protection for SilkRoute.

Blocks requests to private/reserved IP ranges, loopback, link-local,
and file:// scheme. DNS-resolving for hostname-based URLs (fail-open).
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def is_ssrf_blocked(url: str) -> str | None:
    """Return reason string if URL should be SSRF-blocked, else None.

    Blocks:
    - file:// scheme (and any non-http/https)
    - Loopback: 127.x.x.x, ::1, localhost
    - Link-local: 169.254.x.x, fe80::/10
    - RFC 1918 private: 10.x, 172.16-31.x, 192.168.x
    - ULA IPv6: fc00::/7

    DNS resolution is attempted for hostnames (fail-open on DNS errors).
    """
    parsed = urlparse(url)

    # Block non-http(s) schemes (covers file://, ftp://, etc.)
    if parsed.scheme.lower() not in ("http", "https"):
        if parsed.scheme.lower() == "file":
            return "Blocked: file:// scheme is not allowed"
        return f"Blocked: scheme '{parsed.scheme}' is not allowed (only http/https)"

    hostname = parsed.hostname or ""

    # Block localhost by name
    if hostname.lower() in ("localhost", ""):
        return f"Blocked: loopback hostname '{hostname}' is not allowed"

    # Check if hostname is a literal IP
    try:
        addr = ipaddress.ip_address(hostname)
        return _check_ip(addr, hostname)
    except ValueError:
        pass

    # DNS resolution for non-IP hostnames (fail-open)
    try:
        resolved_ip = socket.gethostbyname(hostname)
        addr = ipaddress.ip_address(resolved_ip)
        reason = _check_ip(addr, f"'{hostname}' resolves to {resolved_ip}")
        return reason
    except (OSError, ValueError):
        # DNS failure — fail-open, allow the request
        return None


def _check_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address, label: str) -> str | None:
    """Check a resolved IP against blocked networks."""
    for network in BLOCKED_NETWORKS:
        if addr in network:
            kind = _classify_ip(addr)
            return f"Blocked: {kind} address {label} is in blocked range {network}"
    return None


def _classify_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str:
    """Return a human-readable classification for a blocked IP."""
    if addr.is_loopback:
        return "loopback"
    if addr.is_link_local:
        return "link-local"
    if addr.is_private:
        return "private/RFC-1918"
    return "reserved"
