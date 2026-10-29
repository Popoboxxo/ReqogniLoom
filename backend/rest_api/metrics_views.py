"""
COMP-RA-001 — MetricsViewSet (REQ-L2-SM-001).

REST endpoint for SeMetrics compute_metrics proxy + the central statistics
catalogue (Issue #1265).

Endpoints:
  GET    /api/v1/metrics/          — metrics for a workspace
                                     (?workspace_id=…&type=…&timeframe=…)
                                     Existing shape (stable MetricsResult),
                                     unchanged and additive.
  GET    /api/v1/metrics/?keys=…   — only the named statistics *values*
                                     (Issue #1265). Additive: the envelope is
                                     returned only when ``keys`` is present.
  GET    /api/v1/metrics/catalog/  — the available statistics (Issue #1265).

Issue #1265: the catalogue lives in ``se_metrics.registry`` and is served
identically by REST and MCP, so there is exactly one description of what a
statistic is and how it is queried.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from drf_spectacular.drainage import set_override
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    PolymorphicProxySerializer,
    extend_schema,
)
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import NotAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from application.base import NotFoundError
from application.workspace_service import WorkspaceService
from rest_api.auth_enforcer import get_auth_context
from rest_api.platform_schema_serializers import (
    MetricCatalogueSerializer,
    MetricValuesEnvelopeSerializer,
    MetricsReportSerializer,
)
from rest_api.serializers import build_error_response, detect_lang
from se_metrics.services import (
    compute_metrics,
    get_metric_catalog,
    get_metric_values,
    invalidate_cache,
)

logger = logging.getLogger(__name__)

#: ``refresh`` is opt-in and must be spelled out; anything else is "no refresh".
_TRUTHY = frozenset({"1", "true", "yes", "on"})

#: 200 body of ``GET /api/v1/metrics/``: the full report, or — when ``keys`` is
#: given — the narrower values envelope. A ``oneOf`` is the honest description;
#: which arm applies is decided by the request's ``keys`` parameter.
#:
#: ``many=False`` is mandatory here: ``MetricsViewSet.list`` is a ViewSet
#: ``list`` action, and drf-spectacular's list-view heuristic
#: (``AutoSchema._is_list_view``) answers "list" for any ``action == 'list'``
#: GET, which would wrap this object response in a synthetic array. The override
#: is the documented escape hatch for exactly that coercion.
_METRICS_RESPONSE = PolymorphicProxySerializer(
    component_name="MetricsResponse",
    serializers=[MetricsReportSerializer, MetricValuesEnvelopeSerializer],
    resource_type_field_name=None,
)
set_override(_METRICS_RESPONSE, "many", False)


def _is_truthy(raw: str | None) -> bool:
    """Parse an opt-in boolean query parameter (default False)."""
    return raw is not None and str(raw).strip().lower() in _TRUTHY


def _parse_keys(raw: str | None) -> list[str] | None:
    """Split a comma-separated ``keys`` parameter, or None when absent.

    A present-but-blank value yields ``[]``, which
    :func:`se_metrics.registry.normalize_keys` maps to "every registered
    metric" — the same as an explicitly empty selection.
    """
    if raw is None:
        return None
    return [part.strip() for part in str(raw).split(",") if part.strip()]


class MetricsViewSet(ViewSet):
    """REST proxy to compute_metrics service (SeMetrics)."""

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "workspace_id",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="UUID of the workspace to compute for.",
            ),
            OpenApiParameter(
                "type",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Optional metric type filter (e.g. 'coverage').",
            ),
            OpenApiParameter(
                "timeframe",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="ISO-8601 period for the volatility window, e.g. 'P30D'.",
            ),
            OpenApiParameter(
                "keys",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Comma-separated statistic keys. When present the response "
                    "is the values envelope instead of the full report."
                ),
            ),
            OpenApiParameter(
                "refresh",
                type=bool,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Invalidate the cached computation first, forcing an "
                    "on-demand recompute of the expensive metrics."
                ),
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=_METRICS_RESPONSE,
                description=(
                    "The full REQ-L2-SM-012 report, or — when `keys` is given — "
                    "the narrower values envelope (a oneOf, because the shape is "
                    "chosen by the request)."
                ),
            ),
            400: OpenApiResponse(
                description="Missing/malformed workspace_id."
            ),
            401: OpenApiResponse(description="AUTHENTICATION_REQUIRED."),
            404: OpenApiResponse(description="Workspace not in the caller's tenant."),
        },
    )
    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/metrics/ — metrics for a workspace.

        Query parameters:
          workspace_id  (required) — UUID of the workspace
          type          (optional) — metric type filter (e.g. "coverage")
          timeframe     (optional) — ISO-8601 period, e.g. "P30D"
          keys          (optional, #1265) — comma-separated statistic keys.
                          When present the response is the *values envelope*
                          (``{"metrics": {...}, "unknown_keys": [...]}``)
                          instead of the full MetricsResult.
          refresh       (optional, #1265) — invalidate the cached computation
                          before reading, forcing an on-demand recompute.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except NotAuthenticated:
            return _authentication_required(lang)

        # SA-38: this thread-local must be cleared on every exit path (early
        # 400/404 returns included), otherwise a pooled worker thread carries
        # this request's tenant into whichever request runs on it next —
        # same hygiene contract tool_registry.py's try/finally already
        # documents for the MCP side.
        from persistence.tenancy import TenantContext
        TenantContext.set_tenant(ctx.tenant_id)
        try:
            workspace_id = request.query_params.get("workspace_id")
            if not workspace_id:
                return Response(
                    build_error_response("VALIDATION_ERROR", lang, message="workspace_id query parameter is required"),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                workspace_uuid = UUID(str(workspace_id))
            except ValueError:
                return Response(
                    build_error_response("VALIDATION_ERROR", lang, message="workspace_id must be a valid UUID"),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                WorkspaceService().get_workspace(workspace_uuid, ctx)
            except NotFoundError:
                return Response(
                    build_error_response("NOT_FOUND", lang, message=f"Workspace {workspace_id} not found"),
                    status=status.HTTP_404_NOT_FOUND,
                )

            timeframe = request.query_params.get("timeframe")
            keys = _parse_keys(request.query_params.get("keys"))
            refresh = _is_truthy(request.query_params.get("refresh"))

            try:
                # Issue #1265: the values envelope is opt-in via ``keys``; a
                # plain (or refresh-only) read keeps the stable MetricsResult
                # shape so existing clients are unaffected.
                if keys is not None:
                    data = get_metric_values(
                        workspace_id=str(workspace_id),
                        keys=keys,
                        timeframe=timeframe,
                        refresh=refresh,
                    )
                    return Response(data, status=status.HTTP_200_OK)

                if refresh:
                    invalidate_cache(str(workspace_id), timeframe)

                result = compute_metrics(
                    workspace_id=str(workspace_id),
                    timeframe=timeframe,
                    scope_filter=None,
                )
                data = result.to_dict()
                return Response(data, status=status.HTTP_200_OK)
            except Exception:
                # fix #108 / SYSTEMAUDIT-2026-08-27 finding B (CWE-209): compute_metrics
                # aggregates straight over the ORM, so an unmapped failure here is a
                # DatabaseError/ProgrammingError whose str() carries SQL fragments and
                # table/column names. Same policy as rest_api.views._service_error_response:
                # the real detail goes to the log, the client gets the canonical
                # localised message that build_error_response derives from the code.
                logger.exception(
                    "compute_metrics failed for workspace %s", workspace_id
                )
                return Response(
                    build_error_response("INTERNAL_SERVER_ERROR", lang),
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        finally:
            TenantContext.clear_tenant()

    @extend_schema(
        responses={
            200: OpenApiResponse(
                response=MetricCatalogueSerializer,
                description=(
                    "Every registered statistic with its query contract; pure "
                    "registry metadata, no computation."
                ),
            ),
            401: OpenApiResponse(description="AUTHENTICATION_REQUIRED."),
        },
    )
    @action(detail=False, methods=["get"], url_path="catalog")
    def catalog(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/metrics/catalog/ — the available statistics (#1265).

        Authenticated, but tenant- and workspace-independent: the payload is
        pure registry metadata (keys, titles, units, scopes, query contract)
        shared by REST and MCP. No computation, no DB access, so no
        ``TenantContext`` is armed here.
        """
        try:
            get_auth_context(request)
        except NotAuthenticated:
            return _authentication_required(detect_lang(request))

        return Response(get_metric_catalog(), status=status.HTTP_200_OK)


def _authentication_required(lang: str) -> Response:
    """The shared 401 body for every handler in this module."""
    return Response(
        build_error_response("AUTHENTICATION_REQUIRED", lang),
        status=status.HTTP_401_UNAUTHORIZED,
    )
