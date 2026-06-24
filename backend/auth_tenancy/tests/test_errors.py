"""
COMP-AT-001 ErrorResponseFormatter — standardised auth error tests.

Covers REQ-L3-AT001-004 / REQ-L2-AT-010: stable shape, DE/EN localisation,
no leakage of sensitive data, fixed error-code set.
"""
from __future__ import annotations

import pytest

from auth_tenancy.errors import (
    AuthError,
    PermissionDenied,
    build_error_body,
)


def test_error_body_has_required_fields():
    body = build_error_body("token_expired")
    assert set(body) >= {"error", "message", "doc_url"}
    assert body["error"] == "token_expired"


def test_error_body_localises_german():
    body = build_error_body("authentication_required", accept_language="de-DE,en;q=0.8")
    assert "erforderlich" in body["message"].lower()


def test_error_body_defaults_to_english():
    body = build_error_body("authentication_required", accept_language="fr-FR")
    assert "required" in body["message"].lower()


def test_permission_denied_includes_required_role():
    body = build_error_body(
        "insufficient_permissions", required_role="admin"
    )
    assert body.get("required_role") == "admin"


def test_unknown_error_code_rejected():
    with pytest.raises(ValueError):
        AuthError("not_a_real_code")


def test_permission_denied_status_is_403():
    assert PermissionDenied().status_code == 403


def test_error_body_contains_no_sensitive_markers():
    """No token/hash/stack content leaks into the standardised body."""
    body = build_error_body("invalid_signature")
    serialised = str(body).lower()
    for forbidden in ("traceback", "sha256:", "secret", "eyj"):
        assert forbidden not in serialised
