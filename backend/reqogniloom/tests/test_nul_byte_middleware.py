"""#2087: a NUL byte in a query parameter is a JSON 400, never an HTML 500."""
from __future__ import annotations

from django.http import HttpResponse
from django.test import RequestFactory

from reqogniloom.middleware import NulByteRejectionMiddleware


def _middleware() -> NulByteRejectionMiddleware:
    return NulByteRejectionMiddleware(lambda request: HttpResponse("ok"))


def test_nul_byte_in_query_parameter_is_a_json_400() -> None:
    request = RequestFactory().get("/api/v1/requirements/", {"search": "a\x00b"})

    response = _middleware()(request)

    assert response.status_code == 400
    assert response["Content-Type"].startswith("application/json")
    body = response.content.decode()
    assert '"code": "VALIDATION_ERROR"' in body
    assert "NUL" in body


def test_ordinary_query_parameter_passes_through() -> None:
    request = RequestFactory().get("/api/v1/requirements/", {"search": "a b"})

    response = _middleware()(request)

    assert response.status_code == 200
