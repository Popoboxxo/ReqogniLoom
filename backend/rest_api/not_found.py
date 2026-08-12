"""JSON 404 fallback for unknown ``/api/v1/`` routes (issue #460, finding 1).

An unmatched URL never reaches a view, so neither DRF's exception handler nor
``rest_api.error_envelope.reqogniloom_exception_handler`` — both of which only
run *inside* a DRF view — could normalise it. Django's URL resolver rendered
its own ``404.html`` instead, so a caller that merely typo'd a path got
``text/html`` back while every other error on the same API was JSON::

    GET /api/v1/does-not-exist/   ->  <!doctype html> ... <h1>Not Found</h1>
    GET /api/v1/requirements/<unknown-uuid>/
                                  ->  {"error": {"code": "NOT_FOUND", ...}}

Two hooks are needed, because a ``/api/v1/`` request can 404 in two places:

``api_not_found``
    A catch-all view mounted as the *last* pattern in ``reqogniloom.urls``, so
    it only sees paths that no real route claimed. Handles the routing miss
    deterministically — including under ``DEBUG=True``, where Django bypasses
    ``handler404`` in favour of its technical 404 page.

``api_aware_page_not_found``
    Wired as ``handler404``. Covers the second path: an ``Http404`` *raised
    inside a view* and not converted by DRF — e.g. ``PresetGateMixin.
    _guard_preset``, which raises a bare ``Http404`` when the workspace's
    preset hides the endpoint. That escapes to Django's core handler and used
    to render HTML on an otherwise all-JSON API.

Both are scoped to the ``/api/v1/`` prefix on purpose: ``/admin/`` serves a
human-facing HTML app, ``/mcp/`` speaks JSON-RPC with its own error shape, and
the ``/api/schema/`` endpoints are documentation — all three keep Django's
default 404 behaviour.

Implementation notes:

* A plain Django view, not a DRF ``APIView``. DRF would run content
  negotiation against ``DEFAULT_RENDERER_CLASSES`` and answer ``406 Not
  Acceptable`` for a client that sent an ``Accept`` header this API cannot
  satisfy — turning a simple typo into a confusing status code. A
  ``JsonResponse`` is unconditional.
* ``csrf_exempt`` is required. Before this view existed, an unsafe request to
  an unknown path 404ed in the resolver, i.e. *before*
  ``CsrfViewMiddleware.process_view``. Routing it to a real view would newly
  subject it to CSRF enforcement and answer ``403`` instead of ``404`` (DRF's
  ``APIView`` is Django-level CSRF-exempt for the same reason).
* No authentication or permission check. The resolver 404ed anonymous and
  authenticated callers alike, and requiring auth here would newly leak
  "this path is special" and change ``404`` into ``403`` for unauthenticated
  clients.
"""
from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.defaults import page_not_found

from rest_api.serializers import build_error_response, detect_lang

__all__ = ["API_PREFIX", "api_aware_page_not_found", "api_not_found"]

#: Only paths below this prefix get the JSON envelope.
API_PREFIX = "/api/v1/"

_MESSAGE = {
    "en": "The requested API endpoint does not exist.",
    "de": "Der angeforderte API-Endpunkt existiert nicht.",
}


@csrf_exempt
def api_not_found(request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
    """Return the standard error envelope with HTTP 404 for any method.

    Args:
        request: The unmatched request; only used for language detection.
        *args: Ignored — present so the view can be mounted with or without
            captured URL groups.
        **kwargs: Ignored, same reason.

    Returns:
        ``404`` with ``{"error": {"code": "NOT_FOUND", "message", "details"}}``,
        byte-compatible with ``build_error_response`` (REQ-071,
        REQ-L2-RA-009).

    The message is generic and never echoes ``request.path``: the path is
    caller-controlled and reflecting it would create an XSS/log-injection
    vector for no diagnostic benefit (the caller already knows what it asked
    for).
    """
    lang = detect_lang(request)
    return JsonResponse(
        build_error_response(
            "NOT_FOUND", lang, message=_MESSAGE.get(lang, _MESSAGE["en"])
        ),
        status=404,
    )


def api_aware_page_not_found(
    request: HttpRequest, exception: Exception | None = None, **kwargs: Any
) -> HttpResponse:
    """``handler404``: JSON envelope under ``/api/v1/``, Django's page elsewhere.

    Args:
        request: The request whose handling raised ``Http404``.
        exception: The ``Http404`` instance, forwarded by Django.
        **kwargs: Django passes ``template_name``; only relevant to the
            delegated default.

    Returns:
        The REST error envelope for ``/api/v1/`` paths, otherwise whatever
        ``django.views.defaults.page_not_found`` would have returned — so
        ``/admin/`` and ``/mcp/`` keep their existing HTML behaviour.

    Note that ``exception`` is deliberately not surfaced to the client: an
    ``Http404`` raised deep in a view (``PresetGateMixin._guard_preset``, for
    one) carries internal wording that is not part of the API contract.
    """
    if request.path.startswith(API_PREFIX):
        return api_not_found(request)
    return page_not_found(request, exception, **kwargs)
