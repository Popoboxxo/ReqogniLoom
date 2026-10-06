"""Tests for #1166 — DB connection-slot exhaustion maps to a JSON 503.

Covers the three surfaces that share :mod:`reqogniloom.db_errors`:

* the DRF exception handler (``rest_api.error_envelope``) end-to-end over a real
  ``/api/`` route,
* the narrow :class:`reqogniloom.middleware.DatabaseUnavailableMiddleware` for
  plain-Django ``/api/`` views,
* the readiness probe's ``db_unavailable`` dependency detail.

The predicate is intentionally narrow, so the tests also pin that unrelated
``OperationalError``s are never swallowed.
"""
from __future__ import annotations

import json

import pytest
from django.db.utils import OperationalError
from django.test import Client, RequestFactory

from reqogniloom.db_errors import (
    DB_UNAVAILABLE_CODE,
    is_db_saturation_error,
)
from reqogniloom.middleware import DatabaseUnavailableMiddleware
from reqogniloom.version import VersionView
from rest_api.error_envelope import reqogniloom_exception_handler

pytestmark = pytest.mark.django_db

_SATURATION = (
    "FATAL:  remaining connection slots are reserved for roles with the "
    "SUPERUSER attribute"
)
_UNRELATED = 'FATAL:  password authentication failed for user "reqogniloom_app"'


# ---------------------------------------------------------------------------
# Predicate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        _SATURATION,
        "FATAL:  sorry, too many clients already",
        "connection refused: too many connections",
    ],
)
def test_saturation_signatures_are_recognised(message: str) -> None:
    assert is_db_saturation_error(OperationalError(message)) is True


def test_unrelated_operational_error_is_not_a_saturation_error() -> None:
    assert is_db_saturation_error(OperationalError(_UNRELATED)) is False


def test_non_operational_error_is_not_a_saturation_error() -> None:
    assert is_db_saturation_error(RuntimeError("remaining connection slots are reserved")) is False


# ---------------------------------------------------------------------------
# DRF exception handler — unit
# ---------------------------------------------------------------------------


def _handler_context() -> dict:
    return {"view": None, "request": None}


def test_exception_handler_maps_saturation_to_503_envelope() -> None:
    response = reqogniloom_exception_handler(OperationalError(_SATURATION), _handler_context())
    assert response is not None
    assert response.status_code == 503
    assert response.data["error"]["code"] == DB_UNAVAILABLE_CODE
    assert isinstance(response.data["error"]["message"], str)
    assert response.data["error"]["message"]
    assert response["Retry-After"] == "1"


def test_exception_handler_still_ignores_unrelated_operational_error() -> None:
    # Must NOT be swallowed into a 503 — an unhandled exception still falls
    # through to Django (DRF's handler returns None for it).
    assert reqogniloom_exception_handler(OperationalError(_UNRELATED), _handler_context()) is None


# ---------------------------------------------------------------------------
# Real /api/ path — end to end through the URL stack
# ---------------------------------------------------------------------------


def test_api_path_returns_json_503_on_db_saturation(monkeypatch) -> None:
    def _raise(self, request, *args, **kwargs):
        raise OperationalError(_SATURATION)

    # VersionView is reachable without auth; the raised OperationalError is a
    # realistic stand-in for the connection-slot failure the load test hit.
    monkeypatch.setattr(VersionView, "get", _raise)

    response = Client().get("/api/v1/version/")

    assert response.status_code == 503
    assert response["Content-Type"].startswith("application/json")
    body = response.json()
    assert body["error"]["code"] == DB_UNAVAILABLE_CODE


# ---------------------------------------------------------------------------
# Narrow middleware — plain-Django /api/ paths and scope limits
# ---------------------------------------------------------------------------


def _middleware() -> DatabaseUnavailableMiddleware:
    return DatabaseUnavailableMiddleware(lambda request: None)


def test_middleware_maps_saturation_on_api_path() -> None:
    request = RequestFactory().get("/api/v1/some/plain/django/view/")
    response = _middleware().process_exception(request, OperationalError(_SATURATION))

    assert response is not None
    assert response.status_code == 503
    assert response["Content-Type"].startswith("application/json")
    # JsonResponse (unlike a Django test-client response) exposes no .json().
    assert json.loads(response.content)["error"]["code"] == DB_UNAVAILABLE_CODE
    assert response["Retry-After"] == "1"


def test_middleware_leaves_non_api_path_to_django() -> None:
    request = RequestFactory().get("/health/ready")
    assert _middleware().process_exception(request, OperationalError(_SATURATION)) is None


def test_middleware_does_not_swallow_unrelated_error_on_api_path() -> None:
    request = RequestFactory().get("/api/v1/version/")
    assert _middleware().process_exception(request, OperationalError(_UNRELATED)) is None


# ---------------------------------------------------------------------------
# Readiness — saturation surfaces as a distinct static detail
# ---------------------------------------------------------------------------


def test_readiness_detail_reports_db_unavailable(monkeypatch) -> None:
    from reqogniloom import health

    def _raise() -> None:
        raise OperationalError(_SATURATION)

    monkeypatch.setattr(health.connection, "ensure_connection", _raise)

    payload, http_status = health._readiness_payload()

    assert http_status == 503
    assert payload["status"] == "degraded"
    assert payload["checks"]["database"] == "error"
    database_dep = next(d for d in payload["dependencies"] if d["name"] == "database")
    assert database_dep["detail"] == "db_unavailable"
    # CWE-209: the raw psycopg text never reaches the anonymous body.
    assert "SUPERUSER" not in str(payload)


def test_readiness_detail_stays_generic_for_other_db_errors(monkeypatch) -> None:
    from reqogniloom import health

    def _raise() -> None:
        raise OperationalError(_UNRELATED)

    monkeypatch.setattr(health.connection, "ensure_connection", _raise)

    payload, _http_status = health._readiness_payload()
    database_dep = next(d for d in payload["dependencies"] if d["name"] == "database")
    assert database_dep["detail"] == "dependency_down"
