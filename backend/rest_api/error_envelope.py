"""Unified ReqFlow error envelope for REST API responses (REQ-071).

Normalises every DRF-handled error to the same envelope the API already uses
for explicit errors (``build_error_response``, REQ-L2-RA-009)::

    {"error": {"code": ..., "message": ..., "details": ..., "request_id": ...}}

Wired via ``REST_FRAMEWORK['EXCEPTION_HANDLER']`` so REST responses stay
consistent with the MCP-server error format.

The handler owns the *shape* for the whole API (#1081): a response that reaches
a client with a flat ``{"error": "<code>", "message": ...}`` body, or with the
HTTP status number as its ``code``, is a contract divergence from the one form
``build_error_response`` emits. :data:`_STATUS_TO_CODE` is what makes the code
dimension stable too.
"""
from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from reqogniloom.db_errors import db_unavailable_payload, is_db_saturation_error

#: Stable, string error codes for the HTTP statuses DRF answers without an
#: explicit ``code`` of its own (#1081). Before this map existed, every such
#: response carried the *status number* as its code
#: (``{"error": {"code": "401", ...}}``), so a client branching on
#: ``body.error.code`` had to match a numeric string that no other layer emits.
#: Every key is a code in ``rest_api.serializers._ERROR_MESSAGES``
#: (REQ-L2-RA-004), so code and localised message come from one registry and a
#: client can enumerate the whole code space from it. A status outside the map
#: keeps the numeric fallback — a wrong-but-honest code beats inventing a new
#: public contract for an unforeseen status.
_STATUS_TO_CODE: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "VALIDATION_ERROR",
    status.HTTP_401_UNAUTHORIZED: "AUTHENTICATION_REQUIRED",
    status.HTTP_403_FORBIDDEN: "PERMISSION_DENIED",
    status.HTTP_404_NOT_FOUND: "NOT_FOUND",
    status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
    status.HTTP_409_CONFLICT: "CONFLICT",
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: "UNSUPPORTED_MEDIA_TYPE",
    status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMITED",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL_SERVER_ERROR",
    status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
}


def reqogniloom_exception_handler(exc: Exception, context: dict[str, Any]) -> Any:
    """Normalise all DRF errors to the single canonical error envelope.

    R2A-001: an envelope produced while serving a request carries ``request_id``
    from the request context (ADR-014 §1), mirroring the ``X-Request-ID``
    response header. The import is lazy so this module stays importable before
    a request context exists. Direct, request-less handler calls (unit tests)
    keep the historical three-field body — there is no correlation id to
    mirror — while ``build_error_response`` always emits the field (null when
    no request is active). Real HTTP responses therefore always carry the id.
    """
    from reqogniloom.middleware import get_request_id

    request_id = get_request_id()

    # #1166: PostgreSQL connection-slot exhaustion is not a DRF exception, so
    # DRF's own handler returns None and Django would render an HTML 500. Map it
    # explicitly to HTTP 503 + the SAME envelope before delegating.
    if is_db_saturation_error(exc):
        payload = db_unavailable_payload()
        if request_id is not None:
            payload["error"]["request_id"] = request_id
        return Response(
            payload,
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers={"Retry-After": "1"},
        )

    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    data = response.data
    # Already normalised (e.g. by build_error_response or a prior handler call).
    if isinstance(data, dict) and "error" in data:
        if request_id is not None and isinstance(data["error"], dict):
            data["error"].setdefault("request_id", request_id)
        return response

    code = _get_code(response.status_code, data)
    message = _get_message(data)
    response.data = {
        "error": {
            "code": code,
            "message": message,
            "details": data,
            # Only within a request is there a correlation id to mirror.
            **({"request_id": request_id} if request_id is not None else {}),
        }
    }
    return response


def _get_code(status_code: int, data: Any) -> str:
    if isinstance(data, dict):
        raw = data.get("code")
        # A code that is already a non-empty string wins; a missing, empty or
        # purely numeric one is replaced by the registry name for the status.
        if isinstance(raw, str) and raw.strip() and not raw.strip().isdigit():
            return raw
    return _STATUS_TO_CODE.get(status_code, str(status_code))


def _get_message(data: Any) -> str:
    if isinstance(data, dict):
        return str(data.get("detail", data.get("message", data)))
    if isinstance(data, list):
        return "; ".join(str(e) for e in data)
    return str(data)
