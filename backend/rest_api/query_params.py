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
    "INVALID_UUID_TEMPLATE",
    "MISSING_TEMPLATE",
    "parse_bool_param",
    "parse_change_reason",
    "parse_include_deleted",
    "parse_int_param",
    "parse_uuid_param",
    "parse_workspace_id",
    "reject_unknown_query_params",
    "require_non_empty_param",
]

#: Accepted spellings for a true/false query parameter.
_BOOL_TRUE = frozenset({"true", "1", "yes", "on"})
_BOOL_FALSE = frozenset({"false", "0", "no", "off", ""})

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


def parse_include_deleted(query_params: Any) -> bool:
    """Read the ``?include_deleted=`` flag of a list endpoint (GH-443).

    DELETE is a soft-delete for every workflow-backed entity, so each list
    endpoint needs the same opt-in to surface the records it hides by default.
    Three endpoints (architecture, adrs, glossary) already hand-rolled the exact
    same expression; naming it once keeps the remaining ones from drifting to a
    different spelling of "true".

    Accepts ``true``/``1``/``yes``/``on`` in any casing. Unknown values are
    rejected by :func:`reject_unknown_query_params` at the transport boundary;
    this helper keeps its historical "anything else is false" fallback so a
    direct unit-test call cannot raise.

    Args:
        query_params: ``request.query_params`` (any ``.get``-capable mapping).

    Returns:
        ``True`` when soft-deleted records should be included.
    """
    raw = query_params.get("include_deleted", "")
    return str(raw).strip().lower() in _BOOL_TRUE


def parse_bool_param(
    query_params: Any,
    name: str,
    *,
    default: bool | None = False,
) -> bool | None:
    """Parse a strict boolean query parameter.

    Raises:
        ValueError: The parameter is present but not a recognised boolean.
            The message names the parameter and never echoes its value.
    """
    raw = query_params.get(name)
    if raw is None:
        return default
    value = str(raw).strip().lower()
    if value in _BOOL_TRUE:
        return True
    if value in _BOOL_FALSE:
        return False
    raise ValueError(f"'{name}' must be a boolean (true/false).")


def parse_int_param(
    query_params: Any,
    name: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int | None:
    """Parse an optional integer query parameter with bounds.

    Raises:
        ValueError: Not an integer, or outside ``[minimum, maximum]``.
    """
    raw = query_params.get(name)
    if raw is None:
        return None
    try:
        value = int(str(raw))
    except (TypeError, ValueError):
        raise ValueError(f"'{name}' must be an integer.") from None
    if minimum is not None and value < minimum:
        raise ValueError(f"'{name}' must be >= {minimum}.")
    if maximum is not None and value > maximum:
        raise ValueError(f"'{name}' must be <= {maximum}.")
    return value


def reject_unknown_query_params(
    request: Any,
    allowed: Any,
    lang: str = "en",
) -> Response | None:
    """Reject query parameters the endpoint does not declare (C3 / #1668).

    Unknown parameters used to be accepted with 200 and no effect (the same
    class as #1509), so a typo such as ``?alocated=false`` silently returned
    the unfiltered list. The allow-list is derived from the endpoint's own
    ``@list_schema`` declaration, so it cannot drift from the OpenAPI contract.

    Returns ``None`` when the request is valid, otherwise a ready-to-return
    HTTP 400. Parameter *names* may be echoed (they are bounded by the request
    line); values are never echoed.
    """
    allowed_set = frozenset(allowed)
    unknown = sorted(
        key for key in request.query_params.keys() if key not in allowed_set
    )
    if unknown:
        return _validation_error(
            "Unknown query parameter(s): "
            f"{', '.join(unknown)}. Allowed: {', '.join(sorted(allowed_set))}.",
            lang,
        )
    if "include_deleted" in request.query_params:
        try:
            parse_bool_param(request.query_params, "include_deleted")
        except ValueError as exc:
            return _validation_error(str(exc), lang)
    return None


def parse_change_reason(request: Any) -> str:
    """Resolve the ``change_reason`` of a soft-delete request (G1.5 / #1407).

    The request body stays authoritative; the query string is only a fallback
    for clients that cannot attach a body to ``DELETE`` (browsers, ``fetch``
    based clients, proxies that drop DELETE bodies). Both carriers satisfy the
    same preset gate — without the fallback the gate was simply unreachable for
    those clients, so an Extended-preset workspace answered 400 for a request
    that did carry a reason.

    Returns ``""`` (never ``None``) so the services' ``if not change_reason``
    gate keeps behaving exactly as it did with the body-only read. A non-string
    body value (number, boolean, list) is not a reason and falls through to the
    query string, keeping the ``-> str`` contract.

    A reason taken from the query string is visible in access logs, so clients
    must not put anything sensitive there.

    Accepts a plain Django request as well as a DRF one: the query string is
    read from ``query_params`` when present, else from ``GET``.
    """
    data = getattr(request, "data", None)
    body_reason = data.get("change_reason", "") if isinstance(data, dict) else ""
    if isinstance(body_reason, str) and body_reason:
        return body_reason
    # A raw Django request (e.g. a view called directly in a test) has no DRF
    # ``query_params``; its ``GET`` carries the same query string.
    params = getattr(request, "query_params", None)
    if params is None:
        params = getattr(request, "GET", {})
    return params.get("change_reason") or ""


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
