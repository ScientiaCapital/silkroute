"""Tests for silkroute.network.ssrf — unified SSRF protection."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from silkroute.network.ssrf import is_ssrf_blocked


class TestSchemeBlocking:
    """Block non-http(s) schemes."""

    def test_file_scheme_blocked(self) -> None:
        assert is_ssrf_blocked("file:///etc/passwd") is not None

    def test_ftp_scheme_blocked(self) -> None:
        assert is_ssrf_blocked("ftp://example.com") is not None

    def test_http_allowed(self) -> None:
        assert is_ssrf_blocked("http://example.com") is None

    def test_https_allowed(self) -> None:
        assert is_ssrf_blocked("https://example.com") is None


class TestLocalhostBlocking:
    """Block localhost and loopback."""

    def test_localhost_blocked(self) -> None:
        assert is_ssrf_blocked("http://localhost/path") is not None

    def test_127_0_0_1_blocked(self) -> None:
        assert is_ssrf_blocked("http://127.0.0.1/path") is not None

    def test_ipv6_loopback_blocked(self) -> None:
        assert is_ssrf_blocked("http://[::1]/path") is not None


class TestPrivateRanges:
    """Block RFC 1918 and other private ranges."""

    def test_10_x_blocked(self) -> None:
        assert is_ssrf_blocked("http://10.0.0.1") is not None

    def test_172_16_blocked(self) -> None:
        assert is_ssrf_blocked("http://172.16.0.1") is not None

    def test_192_168_blocked(self) -> None:
        assert is_ssrf_blocked("http://192.168.1.1") is not None

    def test_link_local_blocked(self) -> None:
        assert is_ssrf_blocked("http://169.254.1.1") is not None

    def test_public_ip_allowed(self) -> None:
        assert is_ssrf_blocked("http://8.8.8.8") is None


class TestDNSResolution:
    """DNS-resolving SSRF checks for hostnames."""

    @patch("silkroute.network.ssrf.socket.gethostbyname", return_value="10.0.0.1")
    def test_hostname_resolving_to_private_blocked(self, mock_dns) -> None:
        assert is_ssrf_blocked("http://evil.example.com") is not None

    @patch("silkroute.network.ssrf.socket.gethostbyname", return_value="93.184.216.34")
    def test_hostname_resolving_to_public_allowed(self, mock_dns) -> None:
        assert is_ssrf_blocked("http://example.com") is None

    @patch("silkroute.network.ssrf.socket.gethostbyname", side_effect=OSError("DNS failed"))
    def test_dns_failure_fails_open(self, mock_dns) -> None:
        """DNS errors should NOT block the request (fail-open)."""
        assert is_ssrf_blocked("http://unresolvable.test") is None


class TestEdgeCases:
    """Edge cases and reason messages."""

    def test_empty_hostname_blocked(self) -> None:
        assert is_ssrf_blocked("http:///path") is not None

    def test_returns_reason_string(self) -> None:
        reason = is_ssrf_blocked("http://127.0.0.1")
        assert isinstance(reason, str)
        assert "blocked" in reason.lower() or "127" in reason
