"""Shared validation helpers for REST query/body parameters (issue #460).

Every workspace-scoped list endpoint used to hand-roll the same two lines::

    workspace_id_str = request.query_params.get("workspace_id")
    if not workspace_id_str:
        return Response(build_error_response(..., "workspace_id is required"), 400)

and then either passed the raw string straight into the service layer or
called ``UUID(workspace_id_str)`` inside a ``try`` whose ``except`` clauses did
not list ``ValueError``. Both variants misbehaved for a syntactically invalid
``workspace_id`` (issue #460, finding 2):

* the ORM raised ``django.core.exceptions.ValidationError`` deep inside
  ``QuerySet.filter()`` and the generic ``except Exception`` mapped it onto
  **HTTP 500** (e.g. ``/api/v1/needs/?workspace_id=kaputt``);
* where ``ValueError`` *was* caught, the client got the raw
  ``"badly formed hexadecimal UUID string"`` text, which never names the
  offending parameter.

``parse_workspace_id`` centralises the check and — the point of the fix —
distinguishes *missing* from *malformed*, so a caller that sent a typo'd UUID
is no longer told the parameter is absent.

The helpers return ``(value, error_response)`` instead of raising. Most call
sites sit inside a broad ``try/except Exception`` block that would otherwise
swallow a raised exception and turn a 400 back into a 500 — an explicit early
return cannot be caught by accident.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from rest_framework import status
from rest_framework.response import Response

from rest_api.serializers import build_error_response

__all__ = [
    "MISSING_TEMPLATE",
    "INVALID_UUID_TEMPLATE",
    "parse_uuid_param",
    "parse_workspace_id",
    "require_non_empty_param",
]

#: Emitted when a required parameter is absent or empty.
MISSING_TEMPLATE = "{name} is required"
#: Emitted when a required parameter is present but not a well-formed UUID.
INVALID_UUID_TEMPLATE = "{name} must be a valid UUID"


def _validation_error(message: str, lang: str) -> Response:
    """Build a 400 response in the standard error envelope (REQ-L2-RA-009)."""
    return Response(
        build_error_response("VALIDATION_ERROR", lang, message=message),
        status=status.HTTP_400_BAD_REQUEST,
    )


def parse_uuid_param(
    raw: Any,
    lang: str = "en",
    *,
    name: str = "workspace_id",
) -> tuple[UUID | None, Response | None]:
    """Validate a required UUID request parameter.

    Args:
        raw: The value as received from ``query_params``/``request.data``/URL
            kwargs. ``None`` and ``""`` both count as "not supplied".
        lang: Two-letter language code for the error envelope.
        name: Parameter name, used verbatim in the error message.

    Returns:
        ``(uuid, None)`` when *raw* is a well-formed UUID, otherwise
        ``(None, response)`` where ``response`` is a ready-to-return HTTP 400
        carrying the standard error envelope. Exactly one element is ever
        non-``None``.

    The malformed-value branch deliberately does **not** echo *raw* back: it is
    fully caller-controlled and reflecting it into the response body is the
    same reflection hazard already avoided by
    ``BaseEntityViewSet._reject_malformed_uuid_path_kwargs`` (issue #271).
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None, _validation_error(MISSING_TEMPLATE.format(name=name), lang)
    if isinstance(raw, UUID):
        return raw, None
    try:
        return UUID(str(raw)), None
    except (ValueError, AttributeError, TypeError):
        return None, _validation_error(INVALID_UUID_TEMPLATE.format(name=name), lang)


def parse_workspace_id(
    raw: Any, lang: str = "en"
) -> tuple[UUID | None, Response | None]:
    """Validate the ubiquitous ``workspace_id`` parameter.

    Thin alias for :func:`parse_uuid_param` — the parameter appears on ~20
    endpoints and naming it once keeps the message wording identical
    everywhere.
    """
    return parse_uuid_param(raw, lang, name="workspace_id")


def require_non_empty_param(
    raw: Any, lang: str = "en", *, name: str
) -> tuple[str | None, Response | None]:
    """Validate a required free-text parameter (issue #460, finding 3).

    Returns ``(stripped_value, None)`` or ``(None, response)`` with an HTTP 400
    in the standard error envelope. Used where an absent parameter previously
    produced a misleading empty-but-successful 200 response.
    """
    value = "" if raw is None else str(raw).strip()
    if not value:
        return None, _validation_error(MISSING_TEMPLATE.format(name=name), lang)
    return value, None
