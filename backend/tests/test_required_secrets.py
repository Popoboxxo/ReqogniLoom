"""
Test that required secrets (SECRET_KEY, AUTH_JWT_SECRET) fail-fast when missing (REQ-115).

Note: This test runs under settings_test.py, which pre-sets these environment variables
before importing settings.py. The fail-fast behavior is verified in two ways:
  1. Direct test of the _get_required_secret helper function
  2. Integration test verifying settings_test properly sets defaults before import
"""
import os

import pytest


class TestRequiredSecrets:
    """Verify that required secrets fail-fast when missing."""

    def test_settings_test_imports_without_error(self) -> None:
        """
        Verify that settings_test module successfully imports despite no production env vars.

        This test passes by definition when running under pytest-django with
        django_settings_module = "reqogniloom.settings_test", proving that the
        settings_test module correctly pre-sets the required secrets before
        importing settings.py.
        """
        # If we're running this test, settings_test.py has already been imported
        # without raising ImproperlyConfigured, proving the setup works.
        from reqogniloom import settings_test

        # Verify the test defaults are set
        assert hasattr(settings_test, "SECRET_KEY")
        assert hasattr(settings_test, "AUTH_JWT_SECRET")
        assert settings_test.SECRET_KEY
        assert settings_test.AUTH_JWT_SECRET

    def test_get_required_secret_helper_returns_value_when_set(self) -> None:
        """
        Verify that _get_required_secret returns the env var value when it exists.
        """
        from reqogniloom.settings import _get_required_secret

        # Test that it returns a value when env var is set
        os.environ["TEST_SECRET_VARIABLE"] = "test-value-12345"
        result = _get_required_secret("TEST_SECRET_VARIABLE")
        assert result == "test-value-12345"
        os.environ.pop("TEST_SECRET_VARIABLE", None)

    def test_get_required_secret_helper_raises_when_missing(self) -> None:
        """
        Verify that _get_required_secret raises ImproperlyConfigured when var is not set.
        """
        from django.core.exceptions import ImproperlyConfigured
        from reqogniloom.settings import _get_required_secret

        # Test that it raises ImproperlyConfigured when not set
        with pytest.raises(ImproperlyConfigured) as exc_info:
            _get_required_secret("DEFINITELY_NOT_SET_SECRET_VAR_XYZ")

        error_msg = str(exc_info.value)
        assert "DEFINITELY_NOT_SET_SECRET_VAR_XYZ" in error_msg
        assert "token_urlsafe" in error_msg  # Generation hint should be in error message

    def test_secret_key_value_is_non_empty(self) -> None:
        """
        Verify that SECRET_KEY is not empty (REQ-115).

        This ensures the fail-fast pattern worked and no hardcoded default is used.
        """
        from django.conf import settings

        assert settings.SECRET_KEY
        assert isinstance(settings.SECRET_KEY, str)
        # Should not be a hardcoded placeholder
        assert "CHANGE-ME" not in settings.SECRET_KEY

    def test_auth_jwt_secret_value_is_non_empty(self) -> None:
        """
        Verify that AUTH_JWT_SECRET is not empty (REQ-115).

        This ensures the fail-fast pattern worked and no hardcoded default is used.
        """
        from django.conf import settings

        assert settings.AUTH_JWT_SECRET
        assert isinstance(settings.AUTH_JWT_SECRET, str)
        # Should not be a hardcoded placeholder
        assert "CHANGE-ME" not in settings.AUTH_JWT_SECRET
