"""
COMP-AT-001 ErrorResponseFormatter — standardised auth error tests.

Covers REQ-L3-AT001-004 / REQ-L2-AT-010: stable shape, DE/EN localisation,
no leakage of sensitive data, fixed error-code set.

Shape note (systemaudit 2026-08-27, P1 item 13): ``build_error_body`` now emits
the single project-wide envelope
``{"error": {"code", "message", "details"}}`` instead of its former flat
``{"error": "<code>", "message", "doc_url"}``. ``doc_url`` (and ``required_role``
on a 403) moved into ``details[0]``.
"""
from __future__ import annotations

import pytest

from auth_tenancy.errors import (
    AuthError,
    PermissionDenied,
    build_error_body,
)


def test_error_body_uses_the_project_wide_envelope():
    body = build_error_body("token_expired")
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == "token_expired"
    assert body["error"]["message"]


def test_error_body_carries_doc_url_in_details():
    """``doc_url`` survives the unification — as ``details[0]``, not top-level."""
    body = build_error_body("token_expired")
    assert "doc_url" not in body
    assert body["error"]["details"][0]["doc_url"].endswith("/token_expired")


def test_error_body_localises_german():
    body = build_error_body("authentication_required", accept_language="de-DE,en;q=0.8")
    assert "erforderlich" in body["error"]["message"].lower()


def test_error_body_defaults_to_english():
    body = build_error_body("authentication_required", accept_language="fr-FR")
    assert "required" in body["error"]["message"].lower()


def test_permission_denied_includes_required_role():
    body = build_error_body(
        "insufficient_permissions", required_role="admin"
    )
    assert body["error"]["details"][0]["required_role"] == "admin"


def test_required_role_omitted_when_not_supplied():
    """The hint is optional; its absence must not leave a null placeholder."""
    body = build_error_body("insufficient_permissions")
    assert "required_role" not in body["error"]["details"][0]


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
