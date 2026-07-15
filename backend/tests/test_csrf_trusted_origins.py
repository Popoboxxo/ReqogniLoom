"""
CSRF trusted origins configuration tests (REQ-138).

The cookie-based session auth path enforces Django's CSRF origin check.
Without the SPA origins in CSRF_TRUSTED_ORIGINS every state-changing
request (POST/PATCH/PUT/DELETE) from the browser SPA fails with HTTP 403.
"""

from django.conf import settings


class TestCsrfTrustedOrigins:
    """CSRF_TRUSTED_ORIGINS must allow the browser SPA origins (REQ-138)."""

    def test_setting_is_defined(self) -> None:
        assert hasattr(settings, "CSRF_TRUSTED_ORIGINS")
        assert isinstance(settings.CSRF_TRUSTED_ORIGINS, list)

    def test_vite_dev_server_origins_are_trusted(self) -> None:
        assert "http://localhost:5173" in settings.CSRF_TRUSTED_ORIGINS
        assert "http://127.0.0.1:5173" in settings.CSRF_TRUSTED_ORIGINS

    def test_frontend_container_origins_are_trusted(self) -> None:
        assert "http://localhost:3000" in settings.CSRF_TRUSTED_ORIGINS
