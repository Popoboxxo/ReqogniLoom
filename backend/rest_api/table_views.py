"""REST surface for the artifact table (Tabellenansicht S1, Task 1.6).

One route, one Layer-2 call chain, **zero ORM lines** here (ADR-01 — the ratchet
in ``rest_api/tests/test_architecture.py`` measures this file):

    GET /api/v1/artifacts/table/?workspace_id=&item_type=&filters=&sort=
                                 &include_deleted=&page=&page_size=

Why an ``APIView`` and not a ``ViewSet`` action
-----------------------------------------------
The path lives on the ``artifacts/`` collection and is *not* an artifact
instance route; a router would read ``table`` as a detail pk
(``artifacts/<pk>/`` matches any non-slash segment). ``rest_api.urls`` therefore
registers this before ``include(router.urls)``, exactly like
``artifacts/bulk-update/`` and ``artifacts/bulk-transition/``.

Contract
--------
* **200** — the requested page: ``{count, next, previous, page_size,
  max_page_size, results}`` with the frozen row shape of ``saved-views/<id>/apply/``
  (``{id, artifact_id, item_type, version, values, locked}``).
* **400** — malformed request: unknown query parameter, missing/invalid
  ``workspace_id`` or ``item_type``, non-JSON or non-compiling
  ``filters``/``sort``. A filter error names the field (and the operator where
  applicable), never silently drops the constraint.
* **403** — the caller holds no read role (``Operation.READ``).
* **404** — the workspace is not the caller's (the workspace guard in the
  service's definition resolve answers first).

``page_size`` follows :class:`rest_api.serializers.StandardPagination` (default
25, capped at 100, both echoed), so a clamped page is visible to the client.

No ``If-Match``/``412`` and no ``ETag``: this is a read with no versioned
representation (the conditional-request gate in ``rest_api/conditional_requests.py``
lists the six ETag-bearing families, this route is not one of them).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.base import ValidationError
from application.table_query_service import TableQueryService, clean_item_type
from rest_api.auth_enforcer import get_auth_context
from rest_api.query_params import (
    parse_include_deleted,
    parse_workspace_id,
    reject_unknown_query_params,
)
from rest_api.serializers import StandardPagination, build_error_response, detect_lang
from rest_api.table_serializers import TablePageSerializer
from rest_api.views import _service_error_response

logger = logging.getLogger(__name__)

__all__ = ["TableQueryView"]

#: Every query parameter the route declares. ``reject_unknown_query_params``
#: compares against this exact set, so the allow-list cannot drift from the
#: OpenAPI declaration below (a typo answers 400 instead of being ignored).
ALLOWED_QUERY_PARAMS: tuple[str, ...] = (
    "workspace_id",
    "item_type",
    "filters",
    "sort",
    "include_deleted",
    "page",
    "page_size",
)

_FILTER_WIRE_FORMAT = (
    "{'<field>': {'op': 'contains'|'in'|'gte'|'lte'|'eq', 'value': ...} "
    "| [<constraint>, ...]} (a list is ANDed; at most 200 values per 'in')"
)
_SORT_WIRE_FORMAT = (
    "[{'field': '<name>', 'dir': 'asc'|'desc'}] (at most 5 terms; "
    "'tree' as the first field orders by the persistent sibling key)"
)


def _bad_request(message: str, lang: str) -> Response:
    return Response(
        build_error_response("VALIDATION_ERROR", lang, message=message),
        status=status.HTTP_400_BAD_REQUEST,
    )


def parse_json_param(raw: str | None, name: str, lang: str) -> Any:
    """Decode a JSON query parameter, or ``None`` when absent.

    Returns a sentinel-free contract: the caller distinguishes "absent" by
    passing ``None`` in. A malformed document answers 400 naming the parameter
    and never echoes its content (it is caller-controlled and unbounded).
    """
    if raw is None or raw == "":
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        raise ValidationError(
            f"'{name}' must be a JSON document; "
            + (
                f"expected {_FILTER_WIRE_FORMAT}"
                if name == "filters"
                else f"expected {_SORT_WIRE_FORMAT}"
            )
        ) from None


class TableQueryView(APIView):
    """GET /api/v1/artifacts/table/ — one page of the artifact table.

    The workspace is explicit (mandatory ``workspace_id``): the table always
    shows one workspace, and the definition that drives columns and filters is
    workspace-scoped. ADR-011 classifies this view as an exception with a
    mandatory ``?workspace_id`` (``auth_tenancy/resource_scope.py``) — the same
    treatment as the saved-view collection.
    """

    pagination_class = StandardPagination

    @extend_schema(
        tags=["artifacts"],
        summary="Query one page of the artifact table",
        description=(
            "Server-side table read over the eight artifact types "
            "(Requirement, StakeholderNeed, ArchitectureElement, TestCase, Adr, "
            "Risk, Issue, GlossaryTerm). Rows are filtered and sorted by the "
            "type-aware filter DSL, scoped to the workspace and the caller's "
            "item-level read rules (a 'none' rule hides the row and its count)."
        ),
        parameters=[
            OpenApiParameter(
                "workspace_id",
                OpenApiTypes.UUID,
                OpenApiParameter.QUERY,
                required=True,
                description="Workspace whose rows are read.",
            ),
            OpenApiParameter(
                "item_type",
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                required=True,
                description="One of the eight table item types.",
            ),
            OpenApiParameter(
                "filters",
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                required=False,
                description=f"JSON filter document: {_FILTER_WIRE_FORMAT}",
            ),
            OpenApiParameter(
                "sort",
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                required=False,
                description=f"JSON sort document: {_SORT_WIRE_FORMAT}",
            ),
            OpenApiParameter(
                "include_deleted",
                OpenApiTypes.BOOL,
                OpenApiParameter.QUERY,
                required=False,
                description="Include soft-deleted (outdated) rows.",
            ),
            OpenApiParameter(
                "page",
                OpenApiTypes.INT,
                OpenApiParameter.QUERY,
                required=False,
                description="1-based page number.",
            ),
            OpenApiParameter(
                "page_size",
                OpenApiTypes.INT,
                OpenApiParameter.QUERY,
                required=False,
                description="Rows per page (default 25, capped at 100).",
            ),
        ],
        responses={
            200: TablePageSerializer,
            400: OpenApiResponse(
                description=(
                    "Unknown query parameter, missing/invalid workspace_id or "
                    "item_type, malformed filters/sort JSON, or a filter that "
                    "names an unknown field/operator/value."
                )
            ),
            403: OpenApiResponse(description="The caller has no read role."),
        },
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)

        rejected = reject_unknown_query_params(
            request, ALLOWED_QUERY_PARAMS, lang=lang
        )
        if rejected is not None:
            return rejected

        workspace_id, error = parse_workspace_id(
            request.query_params.get("workspace_id"), lang
        )
        if error is not None:
            return error

        raw_item_type = request.query_params.get("item_type")
        if not raw_item_type:
            return _bad_request("'item_type' is required.", lang)
        try:
            item_type = clean_item_type(raw_item_type)
        except ValidationError as exc:
            return _service_error_response(exc, lang)

        try:
            filters = parse_json_param(
                request.query_params.get("filters"), "filters", lang
            )
            sort = parse_json_param(request.query_params.get("sort"), "sort", lang)
        except ValidationError as exc:
            return _service_error_response(exc, lang)

        include_deleted = parse_include_deleted(request.query_params)

        service = TableQueryService()
        try:
            ctx = get_auth_context(request)
            attributes = service.attributes(ctx, workspace_id, item_type)
            queryset = service.query(
                ctx,
                workspace_id,
                item_type,
                filters,
                sort,
                include_deleted=include_deleted,
            )
            paginator = self.pagination_class()
            page = paginator.paginate_queryset(queryset, request, view=self)
            rows = service.serialize_rows(
                ctx,
                list(page) if page is not None else list(queryset),
                attributes,
                workspace_id=workspace_id,
            )
            if page is None:  # pragma: no cover - StandardPagination always pages
                return Response({"results": rows})
            return paginator.get_paginated_response(rows)
        except Exception as exc:  # noqa: BLE001 — mapped by _service_error_response
            return _service_error_response(exc, lang)
