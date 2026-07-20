"""
SysEng 2.0 N3 (`traceability.suggest_links`, Phase 4b, first stage) — REST endpoint.

UMSETZUNGSPLAN_SYSENG_2.0.md §3.2 + §4 Phase 4b. Mirrors
``rest_api/audit_views.py::WorkspaceAuditAiReviewView`` (N8): a thin
HTTP <-> service translation over the Layer-2
``application.traceability_suggest_service.TraceabilitySuggestService``
facade (ADR-01 — no direct model/RuleEngine access in the view).

  POST /api/v1/workspaces/<workspace_id>/traceability/suggest-links/
       Run the SE-Auditor, filter findings that name a missing trace link
       (TRACE-P1/-P1b/-P2), and rank each finding's deterministic candidate
       pool via the LLM adapter (mock by default). Read-only / advisory —
       nothing is persisted, and every returned finding/candidate reference
       is resolved against the real audit run and the real candidate search
       (see TraceabilitySuggestService's referential-integrity guarantee).
       No pgvector / embedding dependency anywhere in this codepath (§3.2
       first-stage acceptance criterion). Optional query params: ``scope``
       (document|project|global, default: project) and
       ``scope_artifact_id`` (required when scope=document).
"""
from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.traceability_suggest_service import (
    SuggestLinksResponseError,
    TraceabilitySuggestService,
)
from traceability.audit import AuditScope
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import build_error_response, detect_lang

_VALID_SCOPES = frozenset({"document", "project", "global"})


def _parse_scopes(request: Request) -> list[AuditScope] | None:
    """Build the AuditScope list from query params, or None for the default.

    Mirrors ``rest_api/audit_views.py::_parse_scopes``.
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


class WorkspaceTraceabilitySuggestLinksView(APIView):
    """POST /api/v1/workspaces/<workspace_id>/traceability/suggest-links/ — SysEng 2.0 N3.

    Runs the SE-Auditor (Phase 3) and ranks plausible link targets for
    missing-link findings via the LLM adapter. Advisory only — no data is
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
            result = TraceabilitySuggestService().suggest_links(
                workspace_id, get_auth_context(request), scopes=scopes
            )
            return Response(result.to_dict())
        except NotFoundError as exc:
            return Response(
                build_error_response("NOT_FOUND", lang, message=str(exc)),
                status=status.HTTP_404_NOT_FOUND,
            )
        except PermissionDeniedError as exc:
            return Response(
                build_error_response("PERMISSION_DENIED", lang, message=str(exc)),
                status=status.HTTP_403_FORBIDDEN,
            )
        except SuggestLinksResponseError as exc:
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang, message=str(exc)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except ValidationError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


__all__ = ["WorkspaceTraceabilitySuggestLinksView"]
