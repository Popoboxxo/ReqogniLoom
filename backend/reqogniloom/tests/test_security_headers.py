"""
Security-header regression tests (SEC-008, GitHub #75).

Verifies that responses carry a Content-Security-Policy header (added via
``ContentSecurityPolicyMiddleware``) and that HSTS settings are wired up
correctly (Django's own SecurityMiddleware emits the actual header, so we
assert on the settings values it reads rather than re-testing Django).
"""
from __future__ import annotations

import pytest
from django.test import Client, override_settings


@pytest.mark.django_db
class TestContentSecurityPolicyHeader:
    def test_csp_header_present_on_response(self) -> None:
        client = Client()
        response = client.get("/health/")
        assert response["Content-Security-Policy"] == (
            "default-src 'self'; frame-ancestors 'none'; base-uri 'self'"
        )

    @override_settings(CSP_POLICY="default-src 'none'")
    def test_csp_header_is_configurable(self) -> None:
        client = Client()
        response = client.get("/health/")
        assert response["Content-Security-Policy"] == "default-src 'none'"

    def test_existing_security_headers_untouched(self) -> None:
        # Regression guard: the new middleware must not clobber the headers
        # Django's own SecurityMiddleware/XFrameOptionsMiddleware already add.
        client = Client()
        response = client.get("/health/")
        assert response["X-Frame-Options"] == "DENY"
        assert response["X-Content-Type-Options"] == "nosniff"


class TestHstsSettings:
    def test_hsts_disabled_in_debug_by_default(self, settings) -> None:
        if settings.DEBUG:
            assert settings.SECURE_HSTS_SECONDS == 0

    def test_hsts_settings_are_defined(self, settings) -> None:
        # Must exist regardless of environment (SEC-008 remediation).
        assert hasattr(settings, "SECURE_HSTS_SECONDS")
        assert hasattr(settings, "SECURE_HSTS_INCLUDE_SUBDOMAINS")
        assert hasattr(settings, "SECURE_HSTS_PRELOAD")
