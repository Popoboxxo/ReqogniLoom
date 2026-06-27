"""
COMP-RA-001 — MetricsViewSet (REQ-L2-SM-001).

REST endpoint for SeMetrics compute_metrics proxy.

Endpoints:
  GET    /api/v1/metrics/   — compute metrics for a workspace (?workspace_id=...&type=coverage)
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import build_error_response, detect_lang
from se_metrics.services import compute_metrics


class MetricsViewSet(ViewSet):
    """REST proxy to compute_metrics service (SeMetrics)."""

    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/metrics/ — compute metrics for a workspace.

        Query parameters:
          workspace_id  (required) — UUID of the workspace
          type          (optional) — metric type filter (e.g. "coverage")
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        workspace_id = request.query_params.get("workspace_id")
        if not workspace_id:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="workspace_id query parameter is required"),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = compute_metrics(
                workspace_id=str(workspace_id),
                timeframe=request.query_params.get("timeframe"),
                scope_filter=None,
            )
            data = result.to_dict()
            return Response(data, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang, message=str(exc)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
