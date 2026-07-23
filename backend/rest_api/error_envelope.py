"""Unified ReqFlow error envelope for REST API responses (REQ-071).

Normalises every DRF-handled error to the same envelope the API already uses
for explicit errors (``build_error_response``, REQ-L2-RA-009)::

    {"error": {"code": ..., "message": ..., "details": ...}}

Wired via ``REST_FRAMEWORK['EXCEPTION_HANDLER']`` so REST responses stay
consistent with the MCP-server error format.
"""
from __future__ import annotations

from typing import Any

from rest_framework.views import exception_handler as drf_exception_handler


def reqogniloom_exception_handler(exc: Exception, context: dict[str, Any]) -> Any:
    """Normalise all DRF errors to ``{"error": {"code", "message", "details"}}``."""
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    data = response.data
    # Already normalised (e.g. by build_error_response or a prior handler call).
    if isinstance(data, dict) and "error" in data:
        return response

    code = _get_code(response.status_code, data)
    message = _get_message(data)
    response.data = {
        "error": {
            "code": code,
            "message": message,
            "details": data,
        }
    }
    return response


def _get_code(status_code: int, data: Any) -> str:
    if isinstance(data, dict):
        return str(data.get("code", status_code))
    return str(status_code)


def _get_message(data: Any) -> str:
    if isinstance(data, dict):
        return str(data.get("detail", data.get("message", data)))
    if isinstance(data, list):
        return "; ".join(str(e) for e in data)
    return str(data)
