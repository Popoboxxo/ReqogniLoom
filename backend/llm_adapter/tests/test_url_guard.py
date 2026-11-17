"""SA-33 regression tests — SSRF guard on the admin-configurable base_url.

SYSTEMAUDIT-2026-08-27 §4.6 F9: ``LlmSettings.base_url`` was admin-gated and
``URLField``-validated but had no private-CIDR block, so an admin (or a
compromised admin account) could aim the backend's own HTTP client at the cloud
metadata service or any container on the internal network.

The DNS-rebinding residual risk is documented in ``llm_adapter/url_guard.py``
and deliberately not covered here — there is no fix to test.
"""
from __future__ import annotations

import ipaddress
import socket

import pytest
from django.test import override_settings

from llm_adapter.url_guard import (
    UnsafeOutboundUrlError,
    is_public_address,
    validate_outbound_url,
)

_DENY = dict(LLM_ALLOW_PRIVATE_BASE_URL=False, LLM_BASE_URL_ALLOWED_HOSTS="")


@pytest.fixture
def no_dns(monkeypatch):
    """Fail any DNS lookup, so tests can only pass via IP-literal handling.

    Keeps the suite hermetic: a test asserting that ``169.254.169.254`` is
    blocked must not depend on the CI runner's resolver.
    """

    def _boom(*args, **kwargs):
        raise socket.gaierror("DNS disabled in tests")

    monkeypatch.setattr(socket, "getaddrinfo", _boom)


# ---------------------------------------------------------------------------
# Address classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "address",
    [
        "169.254.169.254",  # cloud instance metadata — the canonical SSRF target
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.0.1",
        "0.0.0.0",
        "::1",
        "fe80::1",
        "fc00::1",
        "::ffff:10.0.0.1",  # IPv4-mapped IPv6 — private despite is_private=False
        "::ffff:127.0.0.1",
    ],
)
def test_non_public_addresses_are_rejected(address):
    assert is_public_address(ipaddress.ip_address(address)) is False


@pytest.mark.parametrize("address", ["8.8.8.8", "1.1.1.1", "2606:4700::1111"])
def test_public_addresses_are_accepted(address):
    assert is_public_address(ipaddress.ip_address(address)) is True


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------


@override_settings(**_DENY)
@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1:11434",
        "http://10.1.2.3:8080",
        "http://192.168.1.10/v1",
        "https://172.20.0.5",
        "http://[::1]:11434",
        "http://[::ffff:169.254.169.254]/",
    ],
)
def test_private_targets_are_blocked(url, no_dns):
    with pytest.raises(UnsafeOutboundUrlError):
        validate_outbound_url(url)


@override_settings(**_DENY)
def test_public_literal_is_allowed(no_dns):
    validate_outbound_url("https://8.8.8.8/v1")


@override_settings(**_DENY)
@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "gopher://127.0.0.1:6379/_INFO",
        "ftp://internal.example.com",
    ],
)
def test_non_http_schemes_are_blocked(url, no_dns):
    with pytest.raises(UnsafeOutboundUrlError):
        validate_outbound_url(url)


@override_settings(**_DENY)
def test_unresolvable_host_is_rejected(no_dns):
    """A host that cannot be verified is refused, not waved through."""
    with pytest.raises(UnsafeOutboundUrlError):
        validate_outbound_url("http://does-not-resolve.invalid/v1")


@override_settings(**_DENY)
def test_blank_value_is_a_no_op(no_dns):
    """Empty means 'no override', not 'an unsafe URL'."""
    validate_outbound_url("")
    validate_outbound_url("   ")


@override_settings(**_DENY)
def test_multi_record_host_is_rejected_if_any_address_is_private(monkeypatch):
    """Checking only the first resolved address would be a bypass."""

    def _fake(host, *args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", _fake)
    with pytest.raises(UnsafeOutboundUrlError):
        validate_outbound_url("http://sneaky.example.com/v1")


# ---------------------------------------------------------------------------
# Escape hatches (self-hosted Ollama must stay possible)
# ---------------------------------------------------------------------------


@override_settings(LLM_ALLOW_PRIVATE_BASE_URL=True, LLM_BASE_URL_ALLOWED_HOSTS="")
def test_flag_permits_private_targets(no_dns):
    """Local dev / opted-in operators keep their self-hosted Ollama."""
    validate_outbound_url("http://127.0.0.1:11434")


@override_settings(
    LLM_ALLOW_PRIVATE_BASE_URL=False, LLM_BASE_URL_ALLOWED_HOSTS="ollama, llm.internal"
)
def test_host_allowlist_is_the_narrow_escape_hatch(no_dns):
    validate_outbound_url("http://ollama:11434")
    validate_outbound_url("http://LLM.INTERNAL/v1")  # case-insensitive

    with pytest.raises(UnsafeOutboundUrlError):
        validate_outbound_url("http://169.254.169.254/")


# ---------------------------------------------------------------------------
# AI-003 — env-sourced base_url must pass the SAME guard as DB writes
# ---------------------------------------------------------------------------


class TestEnvBaseUrlIsValidatedCentrally:
    """AI-003: ``LLM_API_BASE_URL`` / ``LLM_BASE_URL`` flow straight into the
    provider HTTP clients, but the SSRF guard was only invoked on persisted
    ``LlmSettings.base_url`` writes. Config resolution must validate *every*
    source before a provider can issue a request.
    """

    @override_settings(LLM_ALLOW_PRIVATE_BASE_URL=False, LLM_BASE_URL_ALLOWED_HOSTS="")
    @pytest.mark.parametrize(
        "bad_url",
        [
            "http://169.254.169.254/latest/meta-data/",  # cloud metadata
            "http://127.0.0.1:11434",  # loopback
            "file:///etc/passwd",  # non-HTTP scheme
        ],
    )
    def test_env_base_url_is_rejected_before_any_request(self, monkeypatch, bad_url):
        from unittest.mock import patch

        from llm_adapter.providers import get_provider

        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        monkeypatch.setenv("LLM_BASE_URL", bad_url)
        monkeypatch.delenv("LLM_API_BASE_URL", raising=False)

        with patch("requests.post") as mock_post:
            with pytest.raises(UnsafeOutboundUrlError):
                get_provider()
            mock_post.assert_not_called()

    @override_settings(LLM_ALLOW_PRIVATE_BASE_URL=False, LLM_BASE_URL_ALLOWED_HOSTS="")
    def test_resolve_provider_config_rejects_private_env_base_url(self, monkeypatch):
        from llm_adapter.providers import resolve_provider_config

        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        monkeypatch.setenv("LLM_API_BASE_URL", "http://10.0.0.5:8080")
        monkeypatch.delenv("LLM_BASE_URL", raising=False)

        with pytest.raises(UnsafeOutboundUrlError):
            resolve_provider_config()

    @override_settings(LLM_ALLOW_PRIVATE_BASE_URL=False, LLM_BASE_URL_ALLOWED_HOSTS="")
    def test_explicit_config_passed_to_get_provider_is_rejected(self, monkeypatch):
        from llm_adapter.providers import ProviderConfig, get_provider

        monkeypatch.delenv("LLM_API_BASE_URL", raising=False)
        cfg = ProviderConfig(
            provider_name="ollama", api_base_url="http://169.254.169.254/"
        )
        with pytest.raises(UnsafeOutboundUrlError):
            get_provider(cfg)

    @override_settings(
        LLM_ALLOW_PRIVATE_BASE_URL=False, LLM_BASE_URL_ALLOWED_HOSTS="ollama"
    )
    def test_allowlisted_env_base_url_is_permitted(self, monkeypatch):
        from llm_adapter.providers import get_provider

        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        monkeypatch.setenv("LLM_BASE_URL", "http://ollama:11434")
        monkeypatch.delenv("LLM_API_BASE_URL", raising=False)

        provider = get_provider()
        assert provider.PROVIDER_NAME == "ollama"
