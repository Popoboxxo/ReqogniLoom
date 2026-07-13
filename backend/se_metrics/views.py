"""
ARCH-L1-015 SeMetrics — DRF Views (COMP-SM-001 MetricsQueryController).

leaf_id: COMP-SM-001
req_id: REQ-L1-031, REQ-L2-SM-001, REQ-L2-SM-002, REQ-L2-SM-010, REQ-L2-SM-012

Implements:
    GET  /metrics/workspace/{id}              — compute_metrics endpoint (IF-L1-042/043)
    GET  /metrics/workspace/{id}/thresholds   — read threshold config
    PUT  /metrics/workspace/{id}/thresholds   — write threshold config (REQ-L2-SM-007)

URL registration (settings/urls NOT modified per constraint):
    The rest_api app or a URL include() in the project urls.py must register:

        from django.urls import path, include
        path("metrics/", include("se_metrics.urls"))

    or register the views directly. This file exports the view classes and
    a urlpatterns list that rest_api or the project can include.

Auth/Tenant note (REQ-L2-SM-010):
    Full RBAC via AuthAndTenancy (ARCH-L1-011) is not yet implemented.
    Views validate token presence (check Authorization header exists — 401 if absent)
    and set TenantContext from a placeholder so downstream queries are tenant-scoped.
    This is the same pattern used by rest_api (TODO: replace once ARCH-L1-011 is done).

Architecture:
    docs/se/L1/Gesamtsystem/L2/SeMetricsSystem/L2_SeMetricsSystem_Architecture.md
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional
from uuid import UUID

from django.conf import settings
from django.http import JsonResponse
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from persistence.tenancy import TenantContext, TenantContextNotSetError
from se_metrics.services import (
    compute_metrics,
    get_threshold_config,
    save_threshold_config,
)

logger = logging.getLogger(__name__)

# ISO-8601 period pattern: P followed by one or more nD/nW/nM/nY segments
# Simplified to support PnD format (required by REQ-L2-SM-002)
_TIMEFRAME_PATTERN = re.compile(
    r"^P(\d+Y)?(\d+M)?(\d+W)?(\d+D)?(T(\d+H)?(\d+M)?(\d+S)?)?$"
)
_MAX_TIMEFRAME_DAYS = 3650  # ~10 years max


def _validate_timeframe(timeframe: str) -> bool:
    """Return True if timeframe is a valid ISO-8601 duration."""
    return bool(_TIMEFRAME_PATTERN.match(timeframe))


def _set_tenant_from_request(request: Request) -> Optional[UUID]:
    """Set TenantContext from request (placeholder for ARCH-L1-011).

    Uses DEFAULT_TENANT_ID from settings as a placeholder until the
    full AuthAndTenancy middleware is implemented.

    Returns:
        The active tenant UUID, or None if not determinable.
    """
    try:
        tenant_id = getattr(settings, "DEFAULT_TENANT_ID", 1)
        # Convert int to UUID if necessary (settings default is int)
        if isinstance(tenant_id, int):
            # Use a deterministic UUID from the integer
            uuid_str = f"00000000-0000-0000-0000-{tenant_id:012d}"
            tenant_uuid = UUID(uuid_str)
        else:
            tenant_uuid = UUID(str(tenant_id))
        TenantContext.set_tenant(tenant_uuid)
        return tenant_uuid
    except Exception:
        logger.warning("SeMetrics: could not set tenant context", exc_info=True)
        return None


def _check_auth(request: Request) -> bool:
    """Validate that an Authorization header is present (REQ-L2-SM-001).

    Returns True if a token is present, False if request should be rejected (401).
    """
    auth_header = request.headers.get("Authorization", "")
    return bool(auth_header.strip())


# ---------------------------------------------------------------------------
# COMP-SM-001: MetricsQueryController
# GET /metrics/workspace/{workspace_id}
# ---------------------------------------------------------------------------


class WorkspaceMetricsView(APIView):
    """GET /metrics/workspace/{workspace_id}

    COMP-SM-001 MetricsQueryController — REST endpoint adapter.

    leaf_id: COMP-SM-001
    req_id: REQ-L2-SM-001, REQ-L2-SM-002, REQ-L2-SM-010, REQ-L2-SM-012

    Error responses:
        401: Missing or invalid Authorization header
        400: Invalid timeframe or scope_filter parameter
        403: Workspace not accessible to caller's tenant (REQ-L2-SM-010)
        404: Unknown workspace_id (not yet implemented — placeholder 404)
        200: MetricsResult JSON (REQ-L2-SM-012)
    """

    authentication_classes = []  # Replaced by _check_auth (ARCH-L1-011 TODO)
    permission_classes = []

    def get(self, request: Request, workspace_id: str) -> Response:
        """Handle GET /metrics/workspace/{workspace_id}.

        Query parameters:
            timeframe: ISO-8601 period (e.g. P30D). Default: P30D.
            scope_filter: Comma-separated artifact types (reserved).
        """
        # 1. Auth check (REQ-L2-SM-001: 401 if no token)
        if not _check_auth(request):
            return Response(
                {"error": "Authentication required"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # 2. Validate workspace_id format
        try:
            ws_uuid = UUID(str(workspace_id))
        except (ValueError, AttributeError):
            return Response(
                {"error": f"Invalid workspace_id: {workspace_id!r}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 3. Parse and validate timeframe (REQ-L2-SM-002)
        timeframe_param = request.query_params.get("timeframe", None)
        if timeframe_param is not None:
            if not _validate_timeframe(timeframe_param):
                return Response(
                    {"error": "Invalid timeframe format"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            timeframe = timeframe_param
        else:
            timeframe = None  # services.py applies default P30D

        # 4. Parse scope_filter (reserved for v2, accepted but not applied)
        scope_filter_param = request.query_params.get("scope_filter", None)
        scope_filter: Optional[List[str]] = None
        if scope_filter_param:
            scope_filter = [s.strip() for s in scope_filter_param.split(",") if s.strip()]

        # 5. Set tenant context (REQ-L2-SM-010 — tenant isolation)
        tenant_uuid = _set_tenant_from_request(request)
        if tenant_uuid is None:
            return Response(
                {"error": "Tenant context could not be resolved"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # 6. Compute metrics (IF-SM-INT-001: controller → aggregator)
        try:
            result = compute_metrics(
                workspace_id=str(ws_uuid),
                timeframe=timeframe,
                scope_filter=scope_filter,
            )
        except TenantContextNotSetError:
            return Response(
                {"error": "Forbidden"},
                status=status.HTTP_403_FORBIDDEN,
            )
        except Exception:
            logger.error(
                "SeMetrics: unexpected error computing metrics for ws=%s",
                workspace_id,
                exc_info=True,
            )
            return Response(
                {"error": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(result.to_dict(), status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# COMP-SM-001: Threshold configuration endpoints (REQ-L2-SM-007)
# GET/PUT /metrics/workspace/{workspace_id}/thresholds
# ---------------------------------------------------------------------------


class WorkspaceThresholdView(APIView):
    """GET/PUT /metrics/workspace/{workspace_id}/thresholds

    COMP-SM-001 — Threshold configuration REST endpoint.

    leaf_id: COMP-SM-001
    req_id: REQ-L2-SM-007

    GET: Return current threshold config (or 404 if not configured)
    PUT: Create or update threshold config
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request: Request, workspace_id: str) -> Response:
        """GET /metrics/workspace/{workspace_id}/thresholds"""
        if not _check_auth(request):
            return Response(
                {"error": "Authentication required"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            ws_uuid = UUID(str(workspace_id))
        except (ValueError, AttributeError):
            return Response(
                {"error": f"Invalid workspace_id: {workspace_id!r}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        _set_tenant_from_request(request)

        config = get_threshold_config(str(ws_uuid))
        if config is None:
            return Response(
                {"workspace_id": str(ws_uuid), "thresholds": {}},
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "workspace_id": str(ws_uuid),
                "thresholds": {
                    "traceability_coverage_min": config.traceability_coverage_min,
                    "volatility_max_avg": config.volatility_max_avg,
                    "workflow_gaps_max": config.workflow_gaps_max,
                    "open_risks_max_critical": config.open_risks_max_critical,
                },
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request: Request, workspace_id: str) -> Response:
        """PUT /metrics/workspace/{workspace_id}/thresholds"""
        if not _check_auth(request):
            return Response(
                {"error": "Authentication required"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            ws_uuid = UUID(str(workspace_id))
        except (ValueError, AttributeError):
            return Response(
                {"error": f"Invalid workspace_id: {workspace_id!r}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tenant_uuid = _set_tenant_from_request(request)
        if tenant_uuid is None:
            return Response(
                {"error": "Forbidden"},
                status=status.HTTP_403_FORBIDDEN,
            )

        data = request.data
        if not isinstance(data, dict):
            return Response(
                {"error": "Request body must be a JSON object"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate threshold values (REQ-L2-SM-007: invalid type → HTTP 400)
        try:
            traceability_coverage_min = _parse_optional_float(
                data.get("traceability_coverage_min")
            )
            volatility_max_avg = _parse_optional_float(
                data.get("volatility_max_avg")
            )
            workflow_gaps_max = _parse_optional_int(
                data.get("workflow_gaps_max")
            )
            open_risks_max_critical = _parse_optional_int(
                data.get("open_risks_max_critical")
            )
        except (TypeError, ValueError) as exc:
            return Response(
                {"error": f"Invalid threshold value: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        config = save_threshold_config(
            workspace_id=str(ws_uuid),
            tenant_id=str(tenant_uuid),
            traceability_coverage_min=traceability_coverage_min,
            volatility_max_avg=volatility_max_avg,
            workflow_gaps_max=workflow_gaps_max,
            open_risks_max_critical=open_risks_max_critical,
        )

        return Response(
            {
                "workspace_id": str(ws_uuid),
                "thresholds": {
                    "traceability_coverage_min": config.traceability_coverage_min,
                    "volatility_max_avg": config.volatility_max_avg,
                    "workflow_gaps_max": config.workflow_gaps_max,
                    "open_risks_max_critical": config.open_risks_max_critical,
                },
            },
            status=status.HTTP_200_OK,
        )


def _parse_optional_float(value) -> Optional[float]:
    """Parse an optional float threshold value. Raises ValueError on bad type."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Expected a number, got {value!r}")


def _parse_optional_int(value) -> Optional[int]:
    """Parse an optional int threshold value. Raises ValueError on bad type."""
    if value is None:
        return None
    try:
        f = float(value)
        if not f.is_integer():
            raise ValueError(f"Expected an integer, got {value!r}")
        return int(f)
    except (TypeError, ValueError):
        raise ValueError(f"Expected an integer, got {value!r}")


# ---------------------------------------------------------------------------
# URL patterns (to be included by rest_api or project URLs)
# ---------------------------------------------------------------------------

from django.urls import path

urlpatterns = [
    path(
        "workspace/<str:workspace_id>/",
        WorkspaceMetricsView.as_view(),
        name="se-metrics-workspace",
    ),
    path(
        "workspace/<str:workspace_id>/thresholds/",
        WorkspaceThresholdView.as_view(),
        name="se-metrics-thresholds",
    ),
]


__all__ = [
    "WorkspaceMetricsView",
    "WorkspaceThresholdView",
    "urlpatterns",
]
