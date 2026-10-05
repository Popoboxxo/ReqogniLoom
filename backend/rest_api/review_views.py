"""REST surface for the pending-review queue (issue #1089).

Routes, one service, one contract (#1089; collection root added by #1177):

    GET /api/v1/reviews/                     ?workspace_id=<uuid>
    GET /api/v1/reviews/pending/?workspace_id=<uuid>
    GET /api/v1/workspaces/<workspace_id>/reviews/pending/

``/api/v1/reviews/`` is the collection root and the flat ``/reviews/pending/``
is the same :class:`ReviewsPendingView` under a differently-named URL — the
root gives a generic client the resource's natural URL (the SPA shows a review
queue but the bare collection used to 404), while ``pending/`` names the queue.
Neither is a second code path.

Both call :class:`application.review_queue_service.ReviewQueueService`, the
same Layer-2 service the MCP tool ``review.list_pending`` uses — that tool
existed while both REST routes 404'd, which is why a human could not reach its
own review queue. "One source of truth, two transports" is the point: a second
copy of the gate predicate here would drift from the MCP one exactly the way
the proposal state did.

**Approving/rejecting is deliberately NOT re-implemented.** Every item the queue
returns is a workflow-tracked entity, and the existing
``POST /api/v1/<entity>/{pk}/transitions/`` action (REST's
``WorkflowTransitionsMixin``) already performs the transition with the role
gates, ``change_reason`` requirement and signature gate enforced by the
workflow engine. The frontend's proposals queue already drives exactly that
endpoint (``frontend/src/components/Reviews/ReviewsView.tsx`` resolves the
confirm/discard target from the item's own ``allowed_transitions``). A second
``/reviews/pending/<id>/approve/`` route would be a second, weaker
implementation of a decision the state machine owns.

Scoping and permissions
-----------------------

* **Tenant** — the service resolves the workspace through
  ``WorkspaceService.get_workspace``, whose ORM read is tenant-scoped, so a
  workspace in another tenant answers 404 exactly like a non-existent one.
* **Workspace** — required, from the path segment on the nested route and from
  the mandatory ``workspace_id`` query parameter on the flat one. The flat
  route exists because the issue names it and because it matches the
  ``?workspace_id=`` convention every other unscoped list endpoint in this API
  already uses; it is not a second code path (both call one shared handler).
* **Role** — a member of the workspace (any non-suspended ``UserRole`` row) and
  additionally holding one of ``workflow.definition_store.PROPOSED_ROLES``
  (``editor``/``approver``/``admin``). A ``viewer`` is refused: the queue's
  entire content is "things you may act on", and a role that cannot confirm or
  discard any of them has no use for the list.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.review_queue_service import ReviewQueueService
from rest_api.auth_enforcer import get_auth_context
from rest_api.query_params import parse_workspace_id
from rest_api.serializers import (
    StandardPagination,
    build_error_response,
    detect_lang,
)

logger = logging.getLogger(__name__)

#: States the caller may narrow the queue to via ``?state=`` (repeatable,
#: comma-separated). Empty/absent means "every state the workspace tracks".
_STATE_PARAM = "state"


def _parse_states(request: Request) -> list[str] | None:
    """Read the optional ``?state=`` narrowing, or ``None`` for "all states".

    Accepts a repeated parameter and a comma-separated list so a client can
    narrow with either ``?state=proposed&state=in_review`` or
    ``?state=proposed,in_review``. Blank entries are dropped; a parameter that
    is present but yields nothing is treated as "no narrowing" rather than as
    an error, so ``?state=`` behaves like an absent parameter instead of
    silently answering an empty queue.
    """
    raw: list[str] = []
    for value in request.query_params.getlist(_STATE_PARAM):
        raw.extend(part.strip() for part in str(value).split(","))
    states = [s for s in raw if s]
    return states or None


def _parse_item_type(request: Request) -> Optional[str]:
    """Read the optional ``?item_type=`` filter (``None`` = every type)."""
    value = request.query_params.get("item_type")
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _queue_error(exc: Exception, lang: str) -> Response:
    """Map a service exception onto the canonical error envelope (REQ-L2-RA-009)."""
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
    # #697 (CWE-209): an unmapped failure here is a DatabaseError/ProgrammingError
    # whose str() carries SQL fragments. The real cause goes to the log; the client
    # gets the canonical localised message — same policy as
    # ``rest_api.views._service_error_response``.
    logger.exception("Review queue query failed")
    return Response(
        build_error_response("INTERNAL_SERVER_ERROR", lang),
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _pending_response(
    request: Request, workspace_id: UUID, lang: str
) -> Response:
    """Shared handler for both routes.

    Kept as a module function rather than a mixin so the two routes cannot
    diverge — the only difference between them is where the workspace id comes
    from, and that is resolved by the caller before this runs.
    """
    from workflow.definition_store import PROPOSED_ROLES

    try:
        ctx = get_auth_context(request)
        items = ReviewQueueService().list_pending(
            ctx,
            workspace_id=workspace_id,
            item_type=_parse_item_type(request),
            states=_parse_states(request),
            required_roles=PROPOSED_ROLES,
        )
    except Exception as exc:  # noqa: BLE001 — mapped in _queue_error
        return _queue_error(exc, lang)

    paginator = StandardPagination()
    page = paginator.paginate_queryset(items, request, view=None)
    results = [item.to_dict() for item in (page if page is not None else items)]
    if page is None:
        return Response(results)
    return paginator.get_paginated_response(results)


class ReviewsPendingView(APIView):
    """GET /api/v1/reviews/ and /api/v1/reviews/pending/ — pending review queue.

    Registered under both URLs (#1177): the collection root ``reviews/`` and the
    ``reviews/pending/`` alias share this one handler.

    Query parameters:
        ``workspace_id`` (required, UUID) — the workspace to scope to.
        ``item_type``     (optional)       — single workflow type filter.
        ``state``         (optional, repeatable / comma-separated) — narrow to
                          specific workflow states, e.g. ``?state=proposed``
                          for just the AI proposals.
        ``page`` / ``page_size`` — standard offset pagination (25 default,
        100 max).

    Responses: 200 with the ``count/next/previous/page_size/max_page_size/
    results`` envelope; 400 on a missing/malformed ``workspace_id`` or unknown
    query parameter; 403 without a proposal-capable role in the workspace; 404
    for a workspace that does not exist in this tenant.
    """

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        workspace_id, error = parse_workspace_id(
            request.query_params.get("workspace_id"), lang
        )
        if error is not None:
            return error
        return _pending_response(request, workspace_id, lang)


class WorkspaceReviewsPendingView(APIView):
    """GET /api/v1/workspaces/{workspace_id}/reviews/pending/.

    Path-scoped twin of :class:`ReviewsPendingView` with identical semantics
    and response shape — see that class for the query parameters, the
    tenant/workspace/role contract and the reason approving is not duplicated
    here.
    """

    def get(
        self, request: Request, workspace_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        lang = detect_lang(request)
        try:
            workspace_uuid = UUID(str(workspace_id))
        except (ValueError, AttributeError, TypeError):
            # The offending value is never echoed back: it is caller-controlled
            # and reflecting it is the reflection hazard #271 exists to avoid.
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    message="'workspace_id' must be a well-formed UUID.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return _pending_response(request, workspace_uuid, lang)


__all__ = [
    "ReviewsPendingView",
    "WorkspaceReviewsPendingView",
]
