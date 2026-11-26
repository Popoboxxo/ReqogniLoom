"""REST surface for the pending-review queue (issue #1089).

Routes, one service, one contract (#1089; collection root added by #1177):

    GET /api/v1/reviews/                     ?workspace_id=<uuid>
    GET /api/v1/reviews/pending/?workspace_id=<uuid>
    GET /api/v1/workspaces/<workspace_id>/reviews/pending/

``/api/v1/reviews/`` is the collection root and the flat ``/reviews/pending/``
is the same handler under a differently-named URL — the root gives a generic
client the resource's natural URL (the SPA shows a review queue but the bare
collection used to 404), while ``pending/`` names the queue. Both are list
operations, so each publishes its own truthful ``operationId``
(``reviews_list`` / ``reviews_pending_list``); the flat route reaches the one
handler through the behaviour-free subclass
:class:`ReviewsPendingAliasView`, which exists only to carry that second
schema decoration. Neither is a second code path.

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
* **Role** — a member of the workspace (any non-suspended ``UserRole`` row)
  holding the RBAC READ capability (``roles_with_capability(Operation.READ)``,
  i.e. every role). The queue is a pure read (#1594), so a ``viewer`` may see
  what is pending — deciding an item still requires the workflow transition's
  own approval gate. The gate is derived from the same matrix the permission
  catalogue reports, so ``viewer.read == true`` is truthful.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.review_queue_service import ReviewQueueService
from rest_api.auth_enforcer import get_auth_context
from rest_api.platform_schema_serializers import PendingReviewPageSerializer
from rest_api.query_params import parse_workspace_id, reject_unknown_query_params
from rest_api.serializers import (
    StandardPagination,
    build_error_response,
    detect_lang,
)

logger = logging.getLogger(__name__)

#: States the caller may narrow the queue to via ``?state=`` (repeatable,
#: comma-separated). Empty/absent means "every state the workspace tracks".
_STATE_PARAM = "state"

# #1362(a): drf-spectacular cannot introspect ``request.query_params.get(...)``
# calls, so ``GET /api/v1/reviews/pending/`` shipped documenting NO parameter
# while *requiring* ``workspace_id`` — a generated client could only produce
# requests the server rejects with 400 ("workspace_id is required"). Same
# contract gap class as #447 (requirement-bundle/search). Declared explicitly;
# keep these lists in sync with the parsing in ``_pending_response``.
_FLAT_QUEUE_PARAMETERS = [
    OpenApiParameter(
        name="workspace_id",
        type=str,
        location=OpenApiParameter.QUERY,
        required=True,
        description="UUID of the workspace to scope the queue to.",
    ),
    OpenApiParameter(
        name="item_type",
        type=str,
        location=OpenApiParameter.QUERY,
        required=False,
        description=(
            "Optional single workflow item-type filter, e.g. 'Requirement' "
            "or 'Adr'. Matched exactly against the workspace's tracked types."
        ),
    ),
    OpenApiParameter(
        name=_STATE_PARAM,
        type=str,
        location=OpenApiParameter.QUERY,
        required=False,
        many=True,
        description=(
            "Optional workflow-state narrowing; repeatable and/or "
            "comma-separated, e.g. ``?state=proposed`` for just the AI "
            "proposals. Omitted = every state the workspace tracks."
        ),
    ),
]

#: The path-scoped twin receives the workspace id from its URL segment, so it
#: declares only the two optional query parameters.
_PATH_SCOPED_QUEUE_PARAMETERS = [
    p for p in _FLAT_QUEUE_PARAMETERS if p.name != "workspace_id"
]

#: ``StandardPagination``'s two query parameters. Declared here because the
#: queue paginates through a bare ``StandardPagination()`` instance rather than a
#: ``pagination_class``, so drf-spectacular cannot discover them (#1388).
_PAGINATION_PARAMETERS = [
    OpenApiParameter(
        name="page",
        type=int,
        location=OpenApiParameter.QUERY,
        required=False,
        description="1-based page number (default 1).",
    ),
    OpenApiParameter(
        name="page_size",
        type=int,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Items per page (default 25, capped at 100).",
    ),
]

#: Fully-qualified query-parameter allow-lists. The documented contract names
#: an unknown parameter as a 400 (#1668); these sets are what the handlers
#: enforce, derived from the declarations above rather than hand-typed twice.
_FLAT_ALLOWED_PARAMS = frozenset(
    param.name for param in _FLAT_QUEUE_PARAMETERS + _PAGINATION_PARAMETERS
)
_PATH_SCOPED_ALLOWED_PARAMS = frozenset(
    param.name for param in _PATH_SCOPED_QUEUE_PARAMETERS + _PAGINATION_PARAMETERS
)


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


def _parse_item_type(request: Request) -> str | None:
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
    from auth_tenancy.services import Operation, roles_with_capability

    try:
        ctx = get_auth_context(request)
        items = ReviewQueueService().list_pending(
            ctx,
            workspace_id=workspace_id,
            item_type=_parse_item_type(request),
            states=_parse_states(request),
            # #1594: the queue is a pure read, so its gate is the RBAC READ
            # capability — the same source the permission catalogue reports.
            # A viewer may see which decisions are pending; confirming or
            # discarding still requires a workflow transition with its own
            # (approval-gated) roles.
            required_roles=roles_with_capability(Operation.READ),
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
    query parameter; 403 when the caller is not a member of the workspace; 404
    for a workspace that does not exist in this tenant.
    """

    @extend_schema(
        operation_id="reviews_list",
        parameters=_FLAT_QUEUE_PARAMETERS + _PAGINATION_PARAMETERS,
        responses={
            200: OpenApiResponse(
                response=PendingReviewPageSerializer,
                description=(
                    "The queue through the StandardPagination envelope "
                    "(count/next/previous/page_size/max_page_size/results)."
                ),
            ),
            400: OpenApiResponse(
                description="Missing/malformed workspace_id or unknown query parameter."
            ),
            403: OpenApiResponse(
                description="Caller is not a member of the workspace."
            ),
            404: OpenApiResponse(description="Workspace not in this tenant."),
        },
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        # #1668: the documented contract (see the ``400`` response above) makes
        # an unknown query parameter a 400, and this handler used to accept one
        # with 200 and no effect. The allow-list is the set declared in
        # ``_FLAT_QUEUE_PARAMETERS`` + ``_PAGINATION_PARAMETERS``.
        error = reject_unknown_query_params(request, _FLAT_ALLOWED_PARAMS, lang)
        if error is not None:
            return error
        workspace_id, error = parse_workspace_id(
            request.query_params.get("workspace_id"), lang
        )
        if error is not None:
            return error
        return _pending_response(request, workspace_id, lang)


class ReviewsPendingAliasView(ReviewsPendingView):
    """GET /api/v1/reviews/pending/ — the flat alias of the collection root.

    A behaviour-free subclass: the handler is
    :meth:`ReviewsPendingView.get` unchanged (same ``?workspace_id=``
    resolution, same ``ReviewQueueService`` call, same envelope), so the two
    URLs cannot drift.

    The subclass exists **only** so the two routes can carry honest, distinct
    ``operationId``s. ``/reviews/`` and ``/reviews/pending/`` are both *list*
    operations; they used to publish ``reviews_retrieve`` and
    ``reviews_pending_retrieve`` (m-3), which lies to a generated client. Both
    paths are served by one ``get`` method, and ``@extend_schema`` decorates
    the *function*, not the URL — so a single decoration would necessarily give
    them the same ``operationId`` (and drf-spectacular would then de-duplicate
    with a suffix instead). Re-declaring ``get`` here keeps one code path and
    two truthful operation ids.
    """

    @extend_schema(
        operation_id="reviews_pending_list",
        parameters=_FLAT_QUEUE_PARAMETERS + _PAGINATION_PARAMETERS,
        responses={
            200: OpenApiResponse(
                response=PendingReviewPageSerializer,
                description="Identical shape to GET /api/v1/reviews/.",
            ),
            400: OpenApiResponse(
                description="Missing/malformed workspace_id or unknown query parameter."
            ),
            403: OpenApiResponse(
                description="Caller is not a member of the workspace."
            ),
            404: OpenApiResponse(description="Workspace not in this tenant."),
        },
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().get(request, *args, **kwargs)


class WorkspaceReviewsPendingView(APIView):
    """GET /api/v1/workspaces/{workspace_id}/reviews/pending/.

    Path-scoped twin of :class:`ReviewsPendingView` with identical semantics
    and response shape — see that class for the query parameters, the
    tenant/workspace/role contract and the reason approving is not duplicated
    here.
    """

    @extend_schema(
        operation_id="workspaces_reviews_pending_list",
        parameters=_PATH_SCOPED_QUEUE_PARAMETERS + _PAGINATION_PARAMETERS,
        responses={
            200: OpenApiResponse(
                response=PendingReviewPageSerializer,
                description="Identical shape to the flat route's 200.",
            ),
            400: OpenApiResponse(
                description="Malformed workspace_id or unknown query parameter."
            ),
            403: OpenApiResponse(
                description="Caller is not a member of the workspace."
            ),
            404: OpenApiResponse(description="Workspace not in this tenant."),
        },
    )
    def get(
        self, request: Request, workspace_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        lang = detect_lang(request)
        # Path-scoped: ``workspace_id`` arrives in the URL segment, so it is not
        # an accepted query parameter here (#1668).
        error = reject_unknown_query_params(
            request, _PATH_SCOPED_ALLOWED_PARAMS, lang
        )
        if error is not None:
            return error
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
    "ReviewsPendingAliasView",
    "ReviewsPendingView",
    "WorkspaceReviewsPendingView",
]
