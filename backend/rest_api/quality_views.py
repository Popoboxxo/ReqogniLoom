"""REST surface for the advisory quality assessment (Plan B / B5-T3, #378).

Two routes over one Layer-2 facade
(:class:`application.quality_service.QualityService`; the view runs no model
query and holds no domain logic, ADR-01):

    POST /api/v1/workspaces/<workspace_id>/quality/assess/
    GET  /api/v1/workspaces/<workspace_id>/quality/<entity_type>/<entity_id>/

They are the REST twin of the MCP ``quality.*`` group and both start from the
service's wire payload (``quality_service.assessment_payload``), so the keys they
share cannot drift; REST adds ``entity_version`` on top (see
:func:`_assessment_payload`, Plan B § B5-T5). ``workspace_id`` comes from the URL
and nowhere else: the service binds every lookup to it, so a foreign-workspace
entity is a 404 and the ADR-011 scope classifier fences the caller's roles
against the same workspace.

Status codes: 201 new / 200 cached verdict, 400 ``VALIDATION_ERROR`` (malformed
body, unassessable type, bad ``limit``), 403 (viewer on the write route), 404
``NOT_FOUND``, 429 (the LLM spend throttle or ``LLM_TOKEN_LIMIT_EXCEEDED``),
502 ``LLM_OUTPUT_INVALID``, 503 ``LLM_UNAVAILABLE``, 504 ``LLM_TIMEOUT`` (the
last four from the shared taxonomy in ``rest_api.views``).
"""
from __future__ import annotations

import logging
from typing import Any

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.quality_service import (
    MAX_HISTORY_LIMIT,
    QualityService,
    assessment_payload as _service_assessment_payload,
)
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import build_error_response, detect_lang
from rest_api.throttling import (
    AuthContextAnonRateThrottle,
    AuthContextUserRateThrottle,
    QualityAssessRateThrottle,
)
from rest_api.views import _service_error_response

logger = logging.getLogger(__name__)


class QualityAssessmentSerializer(serializers.Serializer):
    """Wire form of one assessment (REST and MCP agree on these keys)."""

    assessment_id = serializers.UUIDField()
    entity_type = serializers.CharField()
    entity_id = serializers.UUIDField()
    entity_version = serializers.IntegerField(allow_null=True)
    score = serializers.FloatField(min_value=0.0, max_value=1.0)
    reasoning = serializers.CharField(allow_blank=True)
    suggestions = serializers.ListField(child=serializers.CharField())
    criteria = serializers.DictField(
        child=serializers.FloatField(min_value=0.0, max_value=1.0)
    )
    prompt_slot = serializers.CharField()
    prompt_scope = serializers.CharField()
    provider = serializers.CharField()
    model = serializers.CharField(allow_blank=True)
    trigger = serializers.CharField()
    status = serializers.CharField()
    cached = serializers.BooleanField()
    assessed_at = serializers.CharField()


class QualityAssessRequestSerializer(serializers.Serializer):
    """Body of ``POST .../quality/assess/``."""

    entity_type = serializers.CharField(
        help_text="One of Requirement, Adr, TestCase, Risk."
    )
    entity_id = serializers.UUIDField(help_text="Id of the assessed entity.")
    force = serializers.BooleanField(
        required=False,
        default=False,
        help_text=(
            "Re-run the assessment even when the content is unchanged "
            "(otherwise the last verdict is served from the hash cache)."
        ),
    )


class QualityHistorySerializer(serializers.Serializer):
    """Body of ``GET .../quality/<entity_type>/<entity_id>/``."""

    assessments = QualityAssessmentSerializer(many=True)
    count = serializers.IntegerField()
    latest = QualityAssessmentSerializer(allow_null=True)


def _error(exc: Exception, lang: str) -> Response:
    """Map a service exception onto the canonical error envelope."""
    return _service_error_response(exc, lang)


def _assessment_payload(
    assessment: Any, *, cached: bool = False
) -> dict[str, Any]:
    """REST wire form of one assessment row.

    Wraps the shared builder (``quality_service.assessment_payload``, which the
    MCP ``quality.*`` group also uses) and adds the REST-only ``entity_version``
    key required by Plan B § B5-T5 (``quality-stale-hint``, #378): without the
    revision the verdict refers to, the UI cannot tell a current assessment from
    one pinned to an older content revision. ``null`` means the assessed entity
    carried no version counter.

    Additive only — every key of the shared payload is passed through untouched,
    so the transports still agree on the keys they share.
    """
    payload = _service_assessment_payload(assessment, cached=cached)
    payload["entity_version"] = assessment.entity_version
    return payload


class QualityAssessView(APIView):
    """POST /api/v1/workspaces/<workspace_id>/quality/assess/ — run an assessment.

    Cost guard: the dedicated :class:`QualityAssessRateThrottle` sits next to
    the two generic throttles rather than replacing them, so this LLM-spending
    route keeps the per-caller ceiling every other endpoint has.
    """

    throttle_classes = [
        AuthContextUserRateThrottle,
        AuthContextAnonRateThrottle,
        QualityAssessRateThrottle,
    ]

    @extend_schema(
        request=QualityAssessRequestSerializer,
        responses={
            200: QualityAssessmentSerializer,
            201: QualityAssessmentSerializer,
        },
        description=(
            "Assess one artifact against its type's quality criteria. Answers "
            "201 with a freshly written verdict or 200 with the cached one "
            "(unchanged content, no provider call)."
        ),
    )
    def post(
        self, request: Request, workspace_id: Any, *args: Any, **kwargs: Any
    ) -> Response:
        lang = detect_lang(request)
        body = QualityAssessRequestSerializer(data=request.data)
        if not body.is_valid():
            details = [
                {"field": field, "errors": [str(msg) for msg in messages]}
                for field, messages in body.errors.items()
            ]
            return Response(
                build_error_response("VALIDATION_ERROR", lang, details=details),
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = body.validated_data
        try:
            assessment, cached = QualityService().assess(
                get_auth_context(request),
                workspace_id,
                data["entity_type"],
                data["entity_id"],
                force=bool(data.get("force", False)),
            )
        except Exception as exc:  # noqa: BLE001 — mapped by _error
            return _error(exc, lang)
        return Response(
            _assessment_payload(assessment, cached=cached),
            status=status.HTTP_200_OK if cached else status.HTTP_201_CREATED,
        )


class QualityHistoryView(APIView):
    """GET .../quality/<entity_type>/<entity_id>/?limit=20 — verdict history."""

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="limit",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    f"Page size, 1..{MAX_HISTORY_LIMIT} (default 20), "
                    "newest first."
                ),
            ),
        ],
        responses={200: QualityHistorySerializer},
    )
    def get(
        self,
        request: Request,
        workspace_id: Any,
        entity_type: str,
        entity_id: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        lang = detect_lang(request)
        raw_limit = request.query_params.get("limit")
        try:
            limit = 20 if raw_limit in (None, "") else int(raw_limit)
        except (TypeError, ValueError):
            limit = 0  # the service rejects it → 400 VALIDATION_ERROR
        try:
            rows = QualityService().history(
                get_auth_context(request),
                workspace_id,
                entity_type,
                entity_id,
                limit=limit,
            )
        except Exception as exc:  # noqa: BLE001 — mapped by _error
            return _error(exc, lang)
        return Response(
            {
                "assessments": [_assessment_payload(row) for row in rows],
                "count": len(rows),
                "latest": _assessment_payload(rows[0]) if rows else None,
            }
        )
