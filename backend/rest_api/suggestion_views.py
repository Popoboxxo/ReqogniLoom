"""REST surface for the ADR-019 generic suggestion inbox (WP4).

Routes, one service, one contract — the REST twin of the MCP
``suggestion.*`` tool group (WP3), both a thin adapter over the Layer-2 facade
``application.suggestion_service.SuggestionService`` (ADR-01):

    GET  /api/v1/suggestions/?workspace_id=<uuid>
    POST /api/v1/suggestions/<suggestion_id>/accept/
    POST /api/v1/suggestions/<suggestion_id>/reject/

``SuggestionService`` owns the lifecycle; this module does no domain work. It
resolves the authenticated ``AuthContext``, maps the service's exception
taxonomy onto the canonical error envelope (REQ-L2-RA-009) and returns the
serialized receipt. Accept/reject delegate to the existing per-kind domain path
(for ``trace_link`` the M2 ``confirm_proposed_link`` / ``discard_proposed_link``)
and never reimplement a state transition (ADR-019 Decision 2, Zusage 7(b)/(e)).

Scoping and permissions
-----------------------

* **Tenant** — the service arms the thread-local tenant context from ``ctx`` and
  reads through the tenant-scoped manager (RLS at the DB layer), so a foreign
  tenant's suggestion ids and workspace ids are simply absent, never a leak.
* **Workspace** — ``workspace_id`` is mandatory on the list (the flat
  ``?workspace_id=`` convention every other unscoped list endpoint uses) and
  scopes the caller's roles to it. On accept/reject the workspace is **derived
  from the suggestion row**, not from the request: the ``resource_scope``
  classification of ``SuggestionAcceptView``/``SuggestionRejectView``
  (``entity_key="suggestion"``, ``id_kwargs=("suggestion_id",)``) makes the
  object the authority, so a caller without a role in the suggestion's
  workspace is denied and a foreign tenant's id resolves to nothing (404). The
  views therefore do **not** parse a ``?workspace_id=`` scope hint — see
  ``suggestion_service``/``resource_scope`` for the resolution.
* **Role** — the global ``RbacPermission`` gate maps GET to ``Operation.READ``
  and POST to ``Operation.WRITE``, so a ``viewer`` may read the inbox but only an
  ``editor``/``approver``/``admin`` may accept/reject. The service re-asserts
  both, so the two transports cannot drift.

Error taxonomy (review finding ADR-019 ``003-01``, mirrored by MCP)
-------------------------------------------------------------------

The two ADR-019 anchors are registered in the shared
``rest_api.views._EXC_TO_HTTP``/``_EXC_TO_CODE`` map, but
:func:`_suggestion_error` deliberately **does not delegate** to
``rest_api.views._service_error_response``: that helper dispatches on the
*exact* exception type, so a ``ValidationError`` subclass such as
``SuggestionKindNotEnabledError`` (a dormant kind decided by mistake) would
degrade to a 500. ``_suggestion_error`` instead orders its ``isinstance``
checks so the two anchors win over their generic parent — the same policy
``rest_api.review_views._queue_error`` uses. The codes/statuses below are kept
in sync with the shared map by hand:

* ``AgentSelfConfirmError`` -> **403** ``PERMISSION_DENIED`` — an agent may not
  accept/reject its own proposal (Zusage 7(c)).
* ``ProducerContextRequiredError`` -> **409** ``PRODUCER_CONTEXT_REQUIRED`` —
  a non-agent/non-API-key production attempt fails closed (Zusage 7(f)).
* ``PermissionDeniedError`` -> 403, ``NotFoundError`` -> 404, any other
  ``ValidationError`` -> 400.
"""
from __future__ import annotations

import logging
from typing import Any

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ProducerContextRequiredError,
    ValidationError,
)
from application.suggestion_service import SuggestionService
from application.trace_link_service import AgentSelfConfirmError
from rest_api.auth_enforcer import get_auth_context
from rest_api.query_params import parse_workspace_id
from rest_api.serializers import (
    StandardPagination,
    build_error_response,
    detect_lang,
)

logger = logging.getLogger(__name__)


def _suggestion_error(exc: Exception, lang: str) -> Response:
    """Map a service exception onto the canonical error envelope.

    Mirrors ``rest_api.review_views._queue_error`` and the MCP
    ``SuggestionToolGroup`` mapping. ``AgentSelfConfirmError`` and
    ``ProducerContextRequiredError`` are checked first because they are the two
    ADR-019 taxonomy anchors (403/409) — and because
    ``ProducerContextRequiredError`` is a ``ValidationError`` subclass that must
    not be swallowed by the generic 400 branch below.
    """
    if isinstance(exc, AgentSelfConfirmError):
        return Response(
            build_error_response("PERMISSION_DENIED", lang, message=str(exc)),
            status=status.HTTP_403_FORBIDDEN,
        )
    if isinstance(exc, ProducerContextRequiredError):
        return Response(
            build_error_response(
                "PRODUCER_CONTEXT_REQUIRED", lang, message=str(exc)
            ),
            status=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, PermissionDeniedError):
        return Response(
            build_error_response("PERMISSION_DENIED", lang, message=str(exc)),
            status=status.HTTP_403_FORBIDDEN,
        )
    if isinstance(exc, NotFoundError):
        return Response(
            build_error_response("NOT_FOUND", lang, message=str(exc)),
            status=status.HTTP_404_NOT_FOUND,
        )
    if isinstance(exc, ValidationError):
        return Response(
            build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
            status=status.HTTP_400_BAD_REQUEST,
        )
    # #697 (CWE-209): an unmapped failure's str() can carry SQL fragments.
    # The real cause goes to the log; the client gets the canonical localised
    # message — same policy as rest_api.review_views._queue_error.
    logger.exception("Suggestion request failed")
    return Response(
        build_error_response("INTERNAL_SERVER_ERROR", lang),
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


class SuggestionListView(APIView):
    """GET /api/v1/suggestions/ — the open suggestion inbox of a workspace.

    Query parameters:
        ``workspace_id`` (required, UUID) — the workspace whose inbox is read.
        ``page`` / ``page_size`` — standard offset pagination (25 default,
        100 max), the same ``StandardPagination`` envelope as ``/reviews/``.

    Responses: 200 with the ``count/next/previous/page_size/max_page_size/
    results`` envelope; 400 on a missing/malformed ``workspace_id``; 403
    without at least the ``viewer`` role. A foreign tenant's workspace answers
    an empty page, not a 404 — the tenant-scoped read simply cannot see it.
    """

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        workspace_id, error = parse_workspace_id(
            request.query_params.get("workspace_id"), lang
        )
        if error is not None:
            return error

        try:
            items = SuggestionService().list_open(
                workspace_id, get_auth_context(request)
            )
        except Exception as exc:  # noqa: BLE001 — mapped in _suggestion_error
            return _suggestion_error(exc, lang)

        paginator = StandardPagination()
        page = paginator.paginate_queryset(items, request, view=None)
        results = page if page is not None else items
        if page is None:
            return Response(results)
        return paginator.get_paginated_response(results)


class SuggestionAcceptView(APIView):
    """POST /api/v1/suggestions/<suggestion_id>/accept/ — accept a suggestion.

    Delegates to ``SuggestionService.accept``: the per-kind adapter runs the
    real domain transition (for ``trace_link`` the M2 confirm) and only then
    stamps the receipt ``accepted`` with the server-set ``decided_by``/
    ``decided_at``. Idempotent for an already accepted suggestion.

    The workspace is derived from the suggestion row (object-derived
    authority, see the module docstring); no ``?workspace_id=`` scope hint is
    parsed here.

    Responses: 200 with the serialized receipt; 403 when an agent accepts its
    own proposal (``AgentSelfConfirmError``) or lacks the write role; 404 for a
    suggestion that does not exist in this tenant.
    """

    def post(
        self, request: Request, suggestion_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        lang = detect_lang(request)
        try:
            result = SuggestionService().accept(
                suggestion_id, get_auth_context(request)
            )
        except Exception as exc:  # noqa: BLE001 — mapped in _suggestion_error
            return _suggestion_error(exc, lang)
        return Response(result)


class SuggestionRejectView(APIView):
    """POST /api/v1/suggestions/<suggestion_id>/reject/ — reject a suggestion.

    Delegates to ``SuggestionService.reject``: the per-kind adapter runs the
    existing discard path (for ``trace_link`` the M2 discard removes the
    *proposal link*, never the linked artifacts, Zusage 7(e)) and then stamps
    the receipt ``rejected``. The optional ``reason`` is read from the JSON body
    (falling back to ``?reason=``) and is stored as the audit ``change_reason``.

    Responses: 200 with the serialized receipt; 403 for an agent rejecting its
    own proposal or a caller without the write role; 404 for an unknown
    suggestion.
    """

    def post(
        self, request: Request, suggestion_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        lang = detect_lang(request)
        reason = _parse_reason(request)
        try:
            result = SuggestionService().reject(
                suggestion_id, get_auth_context(request), reason=reason
            )
        except Exception as exc:  # noqa: BLE001 — mapped in _suggestion_error
            return _suggestion_error(exc, lang)
        return Response(result)


def _parse_reason(request: Request) -> str:
    """Read the optional rejection reason from the JSON body or ``?reason=``.

    The body wins; an empty/blank value falls back to the query parameter so a
    client may send either. The value is never trusted for anything but the
    audit ``change_reason`` — it does not influence the domain transition.
    """
    reason = ""
    data = getattr(request, "data", None)
    if isinstance(data, dict):
        reason = str(data.get("reason") or "").strip()
    if not reason:
        reason = str(request.query_params.get("reason") or "").strip()
    return reason


__all__ = [
    "SuggestionAcceptView",
    "SuggestionListView",
    "SuggestionRejectView",
]
