"""REST surface of the on-demand artifact summary (Issue #1792, S1).

One read-only route over one Layer-2 facade
(:class:`application.artifact_summary_service.ArtifactSummaryService`; the view
runs no model query and holds no domain logic, ADR-01):

    GET /api/v1/artifacts/<artifact_id>/summary/

Query parameters:

* ``refresh`` (strict boolean, default ``false``) -- regenerate instead of
  serving a cached answer.
* ``depth`` (integer, default 1) -- trace hops to include; clamped to ``1..2``
  by the service rather than rejected (``0`` behaves like 1, ``7`` like 2).

Status codes: 200 for **every** outcome, including the four degradations --
"feature off" or "provider unavailable" must be distinguishable from "nothing
linked", so they arrive as ``degraded``/``degraded_reason`` and never as
404/403/500 (spec §5.6, §9/E11). 400 ``VALIDATION_ERROR`` for a malformed
``refresh``/``depth``, 403 for a missing role or an item-level deny, 404 for an
unknown artifact (including another tenant's -- no existence leak), 429 from the
dedicated ``artifact_summary`` spend throttle.
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

from application.artifact_summary_service import ArtifactSummaryService
from rest_api.auth_enforcer import get_auth_context
from rest_api.query_params import parse_bool_param, parse_int_param
from rest_api.serializers import build_error_response, detect_lang
from rest_api.throttling import (
    ArtifactSummaryRateThrottle,
    AuthContextAnonRateThrottle,
    AuthContextUserRateThrottle,
)
from rest_api.views import _service_error_response

logger = logging.getLogger(__name__)


class ArtifactSummarySerializer(serializers.Serializer):
    """Wire form of one summary (spec §5.7; MCP ``artifact.summary`` reuses it)."""

    artifact_id = serializers.UUIDField()
    artifact_type = serializers.CharField()
    summary = serializers.CharField(allow_null=True)
    degraded = serializers.BooleanField()
    degraded_reason = serializers.CharField(
        allow_null=True,
        help_text="budget_exhausted | provider_unavailable | stale | disabled",
    )
    cache_hit = serializers.BooleanField()
    trace_depth = serializers.IntegerField()
    neighbour_count = serializers.IntegerField()
    omitted_neighbours = serializers.IntegerField()
    generated_at = serializers.DateTimeField()


class ArtifactSummaryView(APIView):
    """GET /api/v1/artifacts/<artifact_id>/summary/ -- on-demand AI summary.

    Cost guard: the dedicated :class:`ArtifactSummaryRateThrottle` sits next to
    the two generic throttles rather than replacing them, so this
    LLM-spending route keeps the per-caller ceiling every other endpoint has.
    """

    throttle_classes = [
        AuthContextUserRateThrottle,
        AuthContextAnonRateThrottle,
        ArtifactSummaryRateThrottle,
    ]

    @extend_schema(
        tags=["artifacts"],
        summary="AI summary of one artifact and its trace neighbours",
        parameters=[
            OpenApiParameter(
                name="refresh",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Regenerate instead of serving a cached answer for the same "
                    "content (default false)."
                ),
            ),
            OpenApiParameter(
                name="depth",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Trace hops to include: 1 (default) or 2. Values outside "
                    "1..2 are clamped, not rejected."
                ),
            ),
        ],
        responses={
            200: ArtifactSummarySerializer,
            400: OpenApiResponse(description="Malformed 'refresh' or 'depth'."),
            403: OpenApiResponse(
                description="No active role in the artifact's workspace, or an "
                "item-level rule denies read."
            ),
            404: OpenApiResponse(description="Artifact not found."),
            429: OpenApiResponse(description="artifact_summary rate limit exceeded."),
        },
    )
    def get(
        self, request: Request, artifact_id: Any, *args: Any, **kwargs: Any
    ) -> Response:
        lang = detect_lang(request)
        try:
            refresh = bool(
                parse_bool_param(request.query_params, "refresh", default=False)
            )
            depth = parse_int_param(request.query_params, "depth")
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )

        ctx = get_auth_context(request)
        try:
            result = ArtifactSummaryService().summarize_artifact(
                artifact_id, ctx, refresh=refresh, depth=depth
            )
        except Exception as exc:  # noqa: BLE001 -- mapped by _service_error_response
            return _service_error_response(exc, lang)
        return Response(result.as_payload(), status=status.HTTP_200_OK)


__all__ = [
    "ArtifactSummarySerializer",
    "ArtifactSummaryView",
]
