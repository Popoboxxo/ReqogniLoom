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
