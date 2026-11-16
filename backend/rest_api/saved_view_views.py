"""REST surface for saved table views and per-user table state (slice 3, Task 3.3).

Four routes over two Layer-2 facades
(:class:`application.saved_view_service.SavedViewService` /
``TableViewStateService``); **zero ORM lines** here (ADR-01 — the ratchet in
``rest_api/tests/test_architecture.py`` measures this file):

    GET    /api/v1/saved-views/?workspace_id=&item_type=
    POST   /api/v1/saved-views/
    GET    /api/v1/saved-views/<uuid:pk>/
    PATCH  /api/v1/saved-views/<uuid:pk>/
    DELETE /api/v1/saved-views/<uuid:pk>/
    GET    /api/v1/saved-views/<uuid:pk>/apply/
    GET    /api/v1/users/me/table-view-state/?workspace_id=&item_type=
    PUT    /api/v1/users/me/table-view-state/?workspace_id=&item_type=

Contract notes
--------------
* **No ``If-Match``/412.** ``PATCH`` carries ``expected_version`` in the body
  (the plan's conditional-request gate: only Requirement, Document, WorkItem,
  TestCase, Baseline, Workspace and Milestone publish an ``ETag``).
* Errors use the shared envelope: 400 ``VALIDATION_ERROR`` (bad item type,
  unknown field in a filter, oversized state, unknown query parameter),
  403 ``PERMISSION_DENIED`` (no write role / not owner or admin),
  404 ``NOT_FOUND`` (missing, another tenant's, or another user's *private*
  view — no existence leak), 409 ``CONFLICT`` (stale ``expected_version``).
* ``apply`` answers **200** even when the stored documents no longer compile:
  the result is then an empty ``results`` list plus one ``warnings`` entry
  naming the field (plan Review Focus 4). A stale view is not an error.
* The table row shape is shared with ``GET /api/v1/artifacts/table/``
  (``application.table_query_service.TableQueryService.serialize_rows``):
  ``{id, artifact_id, item_type, version, values, locked}``.
"""
from __future__ import annotations

import logging
from typing import Any

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.base import ValidationError
from application.saved_view_service import (
    EMPTY_STATE,
    SavedViewService,
    TableViewStateService,
)
from rest_api.auth_enforcer import get_auth_context
from rest_api.query_params import (
    parse_workspace_id,
    reject_unknown_query_params,
)
from rest_api.serializers import StandardPagination, build_error_response, detect_lang
from rest_api.views import _service_error_response

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Wire serializers (also the OpenAPI schemas)
# ---------------------------------------------------------------------------


class SavedViewSerializer(serializers.Serializer):
    """Wire form of one saved view (REST and MCP share the dict shape)."""

    id = serializers.UUIDField()
    workspace_id = serializers.UUIDField()
    item_type = serializers.CharField()
    owner_id = serializers.UUIDField()
    name = serializers.CharField()
    columns = serializers.ListField(
        child=serializers.DictField(),
        help_text="Ordered column descriptors [{field, order}].",
    )
    filters = serializers.DictField(
        child=serializers.JSONField(),
        help_text="Filter DSL document {'<field>': constraint | [constraint]}.",
    )
    sort = serializers.ListField(
        child=serializers.DictField(),
        help_text="Sort document [{field, dir}].",
    )
    visibility = serializers.ChoiceField(choices=["private", "workspace"])
    version = serializers.IntegerField(help_text="Optimistic-lock counter.")


class SavedViewWriteSerializer(serializers.Serializer):
    """Body of ``POST /saved-views/`` (``workspace_id`` is required)."""

    workspace_id = serializers.UUIDField()
    item_type = serializers.CharField()
    name = serializers.CharField(max_length=255)
    columns = serializers.ListField(child=serializers.DictField(), required=False)
    filters = serializers.DictField(child=serializers.JSONField(), required=False)
    sort = serializers.ListField(child=serializers.DictField(), required=False)
    visibility = serializers.ChoiceField(
        choices=["private", "workspace"], required=False, default="private"
    )


class SavedViewPatchSerializer(serializers.Serializer):
    """Body of ``PATCH /saved-views/<id>/`` (no ``If-Match``, by design)."""

    name = serializers.CharField(max_length=255, required=False)
    columns = serializers.ListField(child=serializers.DictField(), required=False)
    filters = serializers.DictField(child=serializers.JSONField(), required=False)
    sort = serializers.ListField(child=serializers.DictField(), required=False)
    visibility = serializers.ChoiceField(
        choices=["private", "workspace"], required=False
    )
    expected_version = serializers.IntegerField(
        required=False,
        help_text="Stale value answers 409 CONFLICT.",
    )


class SavedViewRowSerializer(serializers.Serializer):
    """One table row, identical to the planned ``artifacts/table/`` row."""

    id = serializers.UUIDField(help_text="Typed entity id (e.g. Requirement id).")
    artifact_id = serializers.UUIDField(help_text="Backing pl_artifact id.")
    item_type = serializers.CharField()
    version = serializers.IntegerField()
    values = serializers.DictField(help_text="Core field values incl. 'uid'.")
    locked = serializers.DictField(
        allow_null=True,
        help_text="Freeze marker; null while the freeze layer does not exist.",
    )


class SavedViewApplySerializer(serializers.Serializer):
    """Paginated ``apply`` body: the standard envelope plus ``warnings``."""

    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    page_size = serializers.IntegerField()
    max_page_size = serializers.IntegerField()
    results = SavedViewRowSerializer(many=True)
    warnings = serializers.ListField(
        child=serializers.CharField(),
        help_text="Why a stored document could not be honoured (empty when ok).",
    )


class TableViewStateSerializer(serializers.Serializer):
    """Body of the per-user table state (GET and PUT)."""

    workspace_id = serializers.UUIDField()
    item_type = serializers.CharField()
    columns = serializers.ListField(child=serializers.DictField())
    filters = serializers.DictField(child=serializers.JSONField())
    sort = serializers.ListField(child=serializers.DictField())


_STATE_QUERY_PARAMS = [
    OpenApiParameter(
        name="workspace_id",
        type=OpenApiTypes.UUID,
        location=OpenApiParameter.QUERY,
        required=True,
        description="Workspace whose table state is read/written.",
    ),
    OpenApiParameter(
        name="item_type",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=True,
        description="Artifact type of the table (e.g. 'Requirement').",
    ),
]


def _error(exc: Exception, lang: str) -> Response:
    """Map a service exception through the shared status/code table."""
    return _service_error_response(exc, lang)


def _bad_request(message: str, lang: str) -> Response:
    return Response(
        build_error_response("VALIDATION_ERROR", lang, message=message),
        status=status.HTTP_400_BAD_REQUEST,
    )


class SavedViewCollectionView(APIView):
    """GET / POST /api/v1/saved-views/ — the caller's readable views of a type."""

    @extend_schema(
        tags=["saved-views"],
        operation_id="saved_views_list",
        summary="List saved table views of a workspace",
        parameters=[
            OpenApiParameter(
                name="workspace_id",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Workspace whose saved views are listed.",
            ),
            OpenApiParameter(
                name="item_type",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Restrict to one artifact type.",
            ),
        ],
        responses={
            200: SavedViewSerializer(many=True),
            400: OpenApiResponse(description="Missing/malformed workspace_id or item_type."),
            403: OpenApiResponse(description="No role in the workspace."),
            404: OpenApiResponse(description="Workspace not found."),
        },
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        rejected = reject_unknown_query_params(
            request, {"workspace_id", "item_type"}, lang
        )
        if rejected is not None:
            return rejected
        workspace_id, error = parse_workspace_id(
            request.query_params.get("workspace_id"), lang
        )
        if error is not None:
            return error
        item_type = request.query_params.get("item_type") or None
        try:
            views = SavedViewService().list(
                get_auth_context(request), workspace_id, item_type
            )
        except Exception as exc:  # noqa: BLE001 — mapped by _service_error_response
            return _error(exc, lang)
        return Response([view.as_payload() for view in views])

    @extend_schema(
        tags=["saved-views"],
        operation_id="saved_views_create",
        summary="Create a saved table view",
        request=SavedViewWriteSerializer,
        responses={
            201: SavedViewSerializer,
            400: OpenApiResponse(description="Unknown item type/field, duplicate name."),
            403: OpenApiResponse(description="No write role in the workspace."),
            404: OpenApiResponse(description="Workspace not found."),
        },
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        body = request.data if isinstance(request.data, dict) else {}
        service = SavedViewService()
        try:
            view = service.create(
                get_auth_context(request),
                workspace_id=body.get("workspace_id"),
                item_type=body.get("item_type"),
                name=body.get("name"),
                columns=body.get("columns"),
                filters=body.get("filters"),
                sort=body.get("sort"),
                visibility=body.get("visibility", "private"),
            )
        except ValidationError as exc:
            return _error(exc, lang)
        except Exception as exc:  # noqa: BLE001
            return _error(exc, lang)
        return Response(view.as_payload(), status=status.HTTP_201_CREATED)


class SavedViewDetailView(APIView):
    """GET / PATCH / DELETE /api/v1/saved-views/<pk>/.

    Authority follows the object (ADR-011): the route names no workspace, the
    scope seam resolves the view's workspace from the row.
    """

    @extend_schema(
        tags=["saved-views"],
        operation_id="saved_views_retrieve",
        summary="Fetch one saved table view",
        responses={
            200: SavedViewSerializer,
            404: OpenApiResponse(description="Not found, or another user's private view."),
        },
    )
    def get(self, request: Request, pk: Any, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            view = SavedViewService().get(get_auth_context(request), pk)
        except Exception as exc:  # noqa: BLE001
            return _error(exc, lang)
        return Response(view.as_payload())

    @extend_schema(
        tags=["saved-views"],
        operation_id="saved_views_partial_update",
        summary="Update a saved table view (no If-Match; expected_version in body)",
        request=SavedViewPatchSerializer,
        responses={
            200: SavedViewSerializer,
            400: OpenApiResponse(description="Invalid name/filters/sort or duplicate name."),
            403: OpenApiResponse(description="Not the owner and not a workspace admin."),
            404: OpenApiResponse(description="Not found."),
            409: OpenApiResponse(description="Stale expected_version."),
        },
    )
    def patch(self, request: Request, pk: Any, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        body = request.data if isinstance(request.data, dict) else {}
        unsupported = sorted(
            set(body)
            - {
                "name",
                "columns",
                "filters",
                "sort",
                "visibility",
                "expected_version",
            }
        )
        if unsupported:
            return _bad_request(
                "Unknown field(s): " + ", ".join(unsupported) + ".", lang
            )
        kwargs_for_update: dict[str, Any] = {}
        for key in ("name", "columns", "filters", "sort", "visibility"):
            if key in body:
                kwargs_for_update[key] = body[key]
        try:
            view = SavedViewService().update(
                get_auth_context(request),
                pk,
                expected_version=body.get("expected_version"),
                **kwargs_for_update,
            )
        except Exception as exc:  # noqa: BLE001
            return _error(exc, lang)
        return Response(view.as_payload())

    @extend_schema(
        tags=["saved-views"],
        operation_id="saved_views_destroy",
        summary="Delete a saved table view",
        responses={
            204: OpenApiResponse(description="Deleted."),
            403: OpenApiResponse(description="Not the owner and not a workspace admin."),
            404: OpenApiResponse(description="Not found."),
        },
    )
    def delete(self, request: Request, pk: Any, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            SavedViewService().delete(get_auth_context(request), pk)
        except Exception as exc:  # noqa: BLE001
            return _error(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SavedViewApplyView(APIView):
    """GET /api/v1/saved-views/<pk>/apply/ — run the stored view.

    Paginates like every other list route (``StandardPagination``: 25 default,
    100 max) and always answers 200 — including the stale-view case, where
    ``results`` is empty and ``warnings`` names the field that stopped
    compiling.
    """

    pagination_class = StandardPagination

    @extend_schema(
        tags=["saved-views"],
        operation_id="saved_views_apply",
        summary="Apply a saved table view (rows + warnings)",
        responses={
            200: SavedViewApplySerializer,
            404: OpenApiResponse(description="Not found, or another user's private view."),
        },
    )
    def get(self, request: Request, pk: Any, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        rejected = reject_unknown_query_params(
            request, {"page", "page_size"}, lang
        )
        if rejected is not None:
            return rejected
        try:
            result = SavedViewService().apply(get_auth_context(request), pk)
            paginator = self.pagination_class()
            page = paginator.paginate_queryset(result.rows, request, view=None)
            rows = page if page is not None else result.rows
            if page is None:
                body: dict[str, Any] = {"results": rows, "warnings": result.warnings}
                return Response(body)
            payload = dict(paginator.get_paginated_response(rows).data)
        except Exception as exc:  # noqa: BLE001
            return _error(exc, lang)
        payload["warnings"] = result.warnings
        return Response(payload)


class UserTableViewStateView(APIView):
    """GET / PUT /api/v1/users/me/table-view-state/ — the caller's own state.

    Self-service: the row is keyed by ``ctx.user_id``, so there is no
    cross-user read path. GET without a stored row answers 200 with the empty
    default (``{columns: [], filters: {}, sort: []}``) instead of 404 — "never
    saved" is a normal state, not a missing resource.
    """

    @extend_schema(
        tags=["saved-views"],
        operation_id="table_view_state_retrieve",
        summary="Read the caller's table state for one workspace/type",
        parameters=_STATE_QUERY_PARAMS,
        responses={
            200: TableViewStateSerializer,
            400: OpenApiResponse(description="Missing/malformed workspace_id or item_type."),
            403: OpenApiResponse(description="No role in the workspace."),
            404: OpenApiResponse(description="Workspace not found."),
        },
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        rejected = reject_unknown_query_params(
            request, {"workspace_id", "item_type"}, lang
        )
        if rejected is not None:
            return rejected
        workspace_id, error = parse_workspace_id(
            request.query_params.get("workspace_id"), lang
        )
        if error is not None:
            return error
        item_type = request.query_params.get("item_type")
        if not item_type:
            return _bad_request("'item_type' is required.", lang)
        try:
            state = TableViewStateService().get(
                get_auth_context(request), workspace_id, item_type
            )
        except Exception as exc:  # noqa: BLE001
            return _error(exc, lang)
        payload = {
            "workspace_id": str(workspace_id),
            "item_type": item_type,
            **(state if state is not None else EMPTY_STATE),
        }
        return Response(payload)

    @extend_schema(
        tags=["saved-views"],
        operation_id="table_view_state_update",
        summary="Upsert the caller's table state for one workspace/type",
        parameters=_STATE_QUERY_PARAMS,
        request=TableViewStateSerializer,
        responses={
            200: TableViewStateSerializer,
            400: OpenApiResponse(description="Bad shape or oversized state (> 32 KiB)."),
            403: OpenApiResponse(description="No write role in the workspace."),
            404: OpenApiResponse(description="Workspace not found."),
        },
    )
    def put(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        rejected = reject_unknown_query_params(
            request, {"workspace_id", "item_type"}, lang
        )
        if rejected is not None:
            return rejected
        workspace_id, error = parse_workspace_id(
            request.query_params.get("workspace_id"), lang
        )
        if error is not None:
            return error
        item_type = request.query_params.get("item_type")
        if not item_type:
            return _bad_request("'item_type' is required.", lang)
        body = request.data if isinstance(request.data, dict) else {}
        unsupported = sorted(set(body) - {"columns", "filters", "sort"})
        if unsupported:
            return _bad_request(
                "Unknown field(s): " + ", ".join(unsupported) + ".", lang
            )
        try:
            state = TableViewStateService().save(
                get_auth_context(request),
                workspace_id,
                item_type,
                columns=body.get("columns"),
                filters=body.get("filters"),
                sort=body.get("sort"),
            )
        except Exception as exc:  # noqa: BLE001
            return _error(exc, lang)
        return Response(
            {
                "workspace_id": str(workspace_id),
                "item_type": item_type,
                **state,
            }
        )
