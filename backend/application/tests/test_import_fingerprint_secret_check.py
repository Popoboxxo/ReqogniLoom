"""Tests for the ADR-014 §7 / D2a import-fingerprint-secret system check."""
from __future__ import annotations

from django.test import override_settings

from application.checks import (
    IMPORT_FINGERPRINT_SECRET_MISSING,
    check_import_fingerprint_secret,
)


def test_warns_when_no_explicit_secret_is_configured() -> None:
    """The SECRET_KEY-derived fallback is surfaced at ``manage.py check`` time."""
    with override_settings(IMPORT_FINGERPRINT_SECRET=""):
        warnings = check_import_fingerprint_secret()

    assert [warning.id for warning in warnings] == [IMPORT_FINGERPRINT_SECRET_MISSING]


def test_quiet_when_an_explicit_secret_is_configured() -> None:
    with override_settings(IMPORT_FINGERPRINT_SECRET="a-dedicated-fingerprint-secret"):
        assert check_import_fingerprint_secret() == []


def test_all_whitespace_secret_still_warns() -> None:
    """A whitespace-only value must trigger the SECRET_KEY fallback and W001.

    Guards the drift fixed for #1128 F3: ``_fingerprint_secret`` stripped the
    setting but the check did not (or vice versa), so
    ``IMPORT_FINGERPRINT_SECRET="   "`` keyed with spaces while silencing W001.
    """
    with override_settings(IMPORT_FINGERPRINT_SECRET="   "):
        warnings = check_import_fingerprint_secret()

    assert [warning.id for warning in warnings] == [IMPORT_FINGERPRINT_SECRET_MISSING]


def test_check_is_registered_with_djangos_check_framework() -> None:
    """``ApplicationConfig.ready()`` must register the check (F4).

    Calling the function directly would pass even if ``ready()`` never
    registered it, silently disabling ``application.W001`` at ``manage.py
    check`` time. Pin the registration in Django's check registry, which is
    populated during app startup.
    """
    from django.core.checks.registry import registry

    assert check_import_fingerprint_secret in registry.registered_checks
