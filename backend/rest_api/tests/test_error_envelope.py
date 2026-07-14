"""Tests for the unified REST error envelope (REQ-071).

Verifies that DRF exceptions are normalised to
``{"error": {"code", "message", "details"}}`` regardless of the raised
exception type, matching the explicit ``build_error_response`` format.
"""
from __future__ import annotations

import pytest
from rest_framework.exceptions import NotFound, ValidationError

from rest_api.error_envelope import reqflow_exception_handler


def _context() -> dict:
    return {"view": None, "request": None}


def test_not_found_wrapped_in_error_envelope() -> None:
    response = reqflow_exception_handler(NotFound(), _context())
    assert response is not None
    assert response.status_code == 404
    assert set(response.data) == {"error"}
    error = response.data["error"]
    assert set(error) == {"code", "message", "details"}
    assert error["code"] == "404"
    assert isinstance(error["message"], str) and error["message"]


def test_validation_error_message_and_details() -> None:
    response = reqflow_exception_handler(
        ValidationError({"title": ["This field is required."]}), _context()
    )
    assert response is not None
    assert response.status_code == 400
    error = response.data["error"]
    assert error["code"] == "400"
    assert error["details"] == {"title": ["This field is required."]}


def test_already_normalised_response_is_passed_through() -> None:
    # An error already shaped like the envelope must not be double-wrapped.
    exc = ValidationError({"error": {"code": "X", "message": "already", "details": []}})
    response = reqflow_exception_handler(exc, _context())
    assert response is not None
    assert response.data == {"error": {"code": "X", "message": "already", "details": []}}


def test_non_drf_exception_returns_none() -> None:
    # Unhandled (non-DRF) exceptions fall through to Django's 500 handler.
    assert reqflow_exception_handler(RuntimeError("boom"), _context()) is None
