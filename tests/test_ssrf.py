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


def _addrinfo(*ips: str):
    """Build a fake getaddrinfo() that returns the given addresses."""
    import socket

    def fake(host, port, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        out = []
        for ip in ips:
            family = socket.AF_INET6 if ":" in ip else socket.AF_INET
            sockaddr = (ip, port or 0, 0, 0) if ":" in ip else (ip, port or 0)
            out.append((family, socket.SOCK_STREAM, 6, "", sockaddr))
        return out

    return fake


class TestDNSResolution:
    """DNS-resolving SSRF checks for hostnames (getaddrinfo, fail-closed)."""

    def test_hostname_resolving_to_private_blocked(self) -> None:
        with patch("silkroute.network.ssrf._getaddrinfo", _addrinfo("10.0.0.1")):
            assert is_ssrf_blocked("http://evil.example.com") is not None

    def test_hostname_resolving_to_public_allowed(self) -> None:
        with patch("silkroute.network.ssrf._getaddrinfo", _addrinfo("93.184.216.34")):
            assert is_ssrf_blocked("http://example.com") is None

    def test_any_private_address_in_answer_blocks(self) -> None:
        """Every returned address is checked, not just the first."""
        fake = _addrinfo("93.184.216.34", "169.254.169.254")
        with patch("silkroute.network.ssrf._getaddrinfo", fake):
            assert is_ssrf_blocked("http://mixed.example.com") is not None

    def test_ipv6_answer_mapped_to_loopback_blocked(self) -> None:
        with patch("silkroute.network.ssrf._getaddrinfo", _addrinfo("::ffff:127.0.0.1")):
            assert is_ssrf_blocked("http://mapped.example.com") is not None

    def test_dns_failure_fails_closed(self) -> None:
        """DNS errors block the request (fail-closed)."""
        with patch("silkroute.network.ssrf._getaddrinfo", side_effect=OSError("DNS failed")):
            assert is_ssrf_blocked("http://unresolvable.test") is not None

    def test_empty_resolution_fails_closed(self) -> None:
        with patch("silkroute.network.ssrf._getaddrinfo", return_value=[]):
            assert is_ssrf_blocked("http://empty.test") is not None


class TestAuditBypasses:
    """Inputs from the security audit that used to pass the guard."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://0.0.0.0:8787/",
            "http://[::]/",
            "http://[::ffff:127.0.0.1]/",
            "http://[::ffff:169.254.169.254]/",
            "http://100.100.100.200/",
            "http://100.64.0.1/",
            "http://100.127.255.254/",
            "http://[2002:7f00:1::]/",
            "http://[::ffff:10.0.0.1]/",
            "http://224.0.0.1/",
            "http://[fe80::1%25eth0]/",
        ],
    )
    def test_bypass_now_blocked(self, url: str) -> None:
        assert is_ssrf_blocked(url) is not None

    @pytest.mark.parametrize(
        "url",
        [
            "http://2130706433/",  # decimal 127.0.0.1
            "http://0x7f000001/",  # hex 127.0.0.1
            "http://0177.0.0.1/",  # octal 127.0.0.1
            "http://127.1/",  # short form
            "http://0xa9fea9fe/",  # hex 169.254.169.254
            "http://localhost./",
            "http://LOCALHOST/",
            "http://foo.localhost/",
        ],
    )
    def test_alternate_encodings_stay_blocked(self, url: str) -> None:
        """Numeric/trailing-dot spellings never reach DNS and stay blocked."""
        with patch("silkroute.network.ssrf._getaddrinfo", _addrinfo("93.184.216.34")):
            assert is_ssrf_blocked(url) is not None

    def test_public_ipv6_allowed(self) -> None:
        assert is_ssrf_blocked("http://[2606:4700:4700::1111]/") is None


class TestEdgeCases:
    """Edge cases and reason messages."""

    def test_empty_hostname_blocked(self) -> None:
        assert is_ssrf_blocked("http:///path") is not None

    def test_returns_reason_string(self) -> None:
        reason = is_ssrf_blocked("http://127.0.0.1")
        assert isinstance(reason, str)
        assert "blocked" in reason.lower() or "127" in reason
