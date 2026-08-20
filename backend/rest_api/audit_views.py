"""
SE-Auditor REST endpoints (SysEng 2.0 Phase 3, "Auditor UI").

UMSETZUNGSPLAN_SYSENG_2.0.md §4, Phase 3. Two endpoints, both workspace-scoped
and Bearer-authenticated, both going exclusively through the Layer-2
``AuditService`` facade (ADR-01 — no direct model/RuleEngine access in the view;
the view only translates HTTP <-> service call):

  GET  /api/v1/workspaces/<workspace_id>/audit/
       Run the SE-Auditor for the workspace and return the findings (grouped by
       the frontend), each with a remediation proposal. The rigor tier is
       resolved from the workspace's active preset by the service. Optional
       query params: ``scope`` (document|project|global, default: project) and
       ``scope_artifact_id`` (required when scope=document).

  POST /api/v1/workspaces/<workspace_id>/audit/remediate/
       Apply the automatic remediation for a single finding (Adopt-Workflow).
       Body: {rule_id, artifact_ids: [...], scope?, scope_artifact_id?}. On
       success returns {applied: true, finding_resolved, created_link_id,
       proposal}. A finding without an unambiguous auto-fix returns HTTP 422
       with the reason (the UI turns this into a "Modify" / manual prompt).

  POST /api/v1/workspaces/<workspace_id>/audit/ai-review/
       SysEng 2.0 N8 (`audit.ai_review`, Phase 4b): run the SE-Auditor and
       bundle its findings into strategic refactoring packages via the LLM
       adapter (mock by default). Read-only / advisory — nothing is
       persisted, and every returned finding reference is resolved against
       the real audit run (see AiReviewService's referential-integrity
       guarantee). Optional query params: same ``scope`` /
       ``scope_artifact_id`` pair as the GET endpoint above.

Module rationale: the codebase splits large view groups into dedicated modules
(settings_views.py, global_default_views.py, diagram_views.py, ...) rather than
growing the 5k-line views.py. This follows that established convention; the
Phase-3 plan's "views.py" is a rough placement hint, not a hard constraint.
"""
from __future__ import annotations

from typing import Any

from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.ai_review_service import AiReviewResponseError, AiReviewService
from application.audit_service import AuditService
from application.base import NotFoundError, PermissionDeniedError, ValidationError
from traceability.audit import AuditScope
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import build_error_response, detect_lang

_VALID_SCOPES = frozenset({"document", "project", "global"})


# ---------------------------------------------------------------------------
# Request serializers (validation only — responses are service DTOs).
# ---------------------------------------------------------------------------


class RemediateRequestSerializer(serializers.Serializer):
    """Body of POST .../audit/remediate/ — identifies one finding to adopt."""

    rule_id = serializers.CharField(max_length=64)
    artifact_ids = serializers.ListField(
        child=serializers.CharField(max_length=64),
        allow_empty=False,
    )
    scope = serializers.ChoiceField(
        choices=sorted(_VALID_SCOPES), required=False, allow_null=True
    )
    scope_artifact_id = serializers.CharField(
        max_length=64, required=False, allow_null=True, allow_blank=True
    )


def _parse_scopes(request: Request) -> list[AuditScope] | None:
    """Build the AuditScope list from query params, or None for the default.

    ``?scope=`` absent -> None (RuleEngine defaults to the project scope).
    ``scope=document`` requires ``scope_artifact_id``; a missing one raises
    ValueError which the caller maps to a 400.
    """
    scope = request.query_params.get("scope")
    if not scope:
        return None
    if scope not in _VALID_SCOPES:
        raise ValueError(f"Invalid scope '{scope}'.")
    artifact_id = request.query_params.get("scope_artifact_id") or None
    if scope == "document" and not artifact_id:
        raise ValueError("scope_artifact_id is required when scope=document.")
    return [AuditScope(scope, artifact_id=artifact_id)]


def _parse_pagination(request: Request) -> tuple[int | None, int]:
    """#622: optional ``?limit=&offset=`` to page past the findings cap.

    Absent ``limit`` -> ``(None, 0)``, preserving the default BLOCKER-
    preferred truncation exactly as before this was added. A present but
    invalid (non-integer) value raises ValueError, mapped to a 400 by the
    caller — same pattern as ``_parse_scopes``.
    """
    raw_limit = request.query_params.get("limit")
    if raw_limit is None:
        return None, 0
    try:
        limit = int(raw_limit)
    except ValueError as exc:
        raise ValueError("limit must be an integer.") from exc
    raw_offset = request.query_params.get("offset", "0")
    try:
        offset = int(raw_offset)
    except ValueError as exc:
        raise ValueError("offset must be an integer.") from exc
    return limit, offset


class WorkspaceAuditView(APIView):
    """GET /api/v1/workspaces/<workspace_id>/audit/ — run the SE-Auditor."""

    def get(
        self, request: Request, workspace_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        lang = detect_lang(request)
        try:
            scopes = _parse_scopes(request)
            limit, offset = _parse_pagination(request)
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            report = AuditService().run_audit(
                workspace_id,
                get_auth_context(request),
                scopes=scopes,
                limit=limit,
                offset=offset,
            )
            return Response(report.to_dict())
        except NotFoundError as exc:
            return Response(
                build_error_response("NOT_FOUND", lang, message=str(exc)),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception:
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class WorkspaceAuditRemediateView(APIView):
    """POST /api/v1/workspaces/<workspace_id>/audit/remediate/ — Adopt-Workflow."""

    def post(
        self, request: Request, workspace_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        lang = detect_lang(request)
        ser = RemediateRequestSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[
                        {"field": k, "errors": v} for k, v in ser.errors.items()
                    ],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = ser.validated_data
        try:
            result = AuditService().remediate(
                workspace_id,
                get_auth_context(request),
                rule_id=data["rule_id"],
                artifact_ids=data["artifact_ids"],
                scope=data.get("scope"),
                scope_artifact_id=data.get("scope_artifact_id") or None,
            )
            return Response(result.to_dict(), status=status.HTTP_200_OK)
        except PermissionDeniedError as exc:
            return Response(
                build_error_response("PERMISSION_DENIED", lang, message=str(exc)),
                status=status.HTTP_403_FORBIDDEN,
            )
        except NotFoundError as exc:
            return Response(
                build_error_response("NOT_FOUND", lang, message=str(exc)),
                status=status.HTTP_404_NOT_FOUND,
            )
        except ValidationError as exc:
            # A finding without an unambiguous auto-fix, or a rejected
            # correction. 422 = "understood, but cannot apply automatically";
            # the UI renders this as a manual "Modify" action.
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except Exception:
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class WorkspaceAuditAiReviewView(APIView):
    """POST /api/v1/workspaces/<workspace_id>/audit/ai-review/ — SysEng 2.0 N8.

    Runs the SE-Auditor (Phase 3) and bundles its findings into strategic
    refactoring packages via the LLM adapter. Advisory only — no data is
    mutated; individual findings are still fixed through the existing
    ``audit/remediate/`` Adopt-Workflow.
    """

    def post(
        self, request: Request, workspace_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        lang = detect_lang(request)
        try:
            scopes = _parse_scopes(request)
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            result = AiReviewService().review(
                workspace_id, get_auth_context(request), scopes=scopes
            )
            return Response(result.to_dict())
        except NotFoundError as exc:
            return Response(
                build_error_response("NOT_FOUND", lang, message=str(exc)),
                status=status.HTTP_404_NOT_FOUND,
            )
        except AiReviewResponseError as exc:
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang, message=str(exc)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception:
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


__all__ = [
    "WorkspaceAuditView",
    "WorkspaceAuditRemediateView",
    "WorkspaceAuditAiReviewView",
]
