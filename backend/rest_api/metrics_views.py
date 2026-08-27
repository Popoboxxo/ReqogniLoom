"""
COMP-RA-001 — MetricsViewSet (REQ-L2-SM-001).

REST endpoint for SeMetrics compute_metrics proxy.

Endpoints:
  GET    /api/v1/metrics/   — compute metrics for a workspace (?workspace_id=...&type=coverage)
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from application.base import NotFoundError
from application.workspace_service import WorkspaceService
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import build_error_response, detect_lang
from se_metrics.services import compute_metrics

logger = logging.getLogger(__name__)


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

        from persistence.tenancy import TenantContext
        TenantContext.set_tenant(ctx.tenant_id)

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

        try:
            result = compute_metrics(
                workspace_id=str(workspace_id),
                timeframe=request.query_params.get("timeframe"),
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
