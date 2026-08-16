"""
SysEng 2.0 N1 (`architecture.decompose`) REST endpoints — Draft-Staging copilot.

UMSETZUNGSPLAN_SYSENG_2.0.md §3.1 + §4 Phase 4a. Two workspace-scoped,
Bearer-authenticated endpoints, both going exclusively through the Layer-2
``ArchitectureDecomposeService`` facade (ADR-01 — the view only translates
HTTP <-> service call, never touches models/RuleEngine directly):

  POST /api/v1/workspaces/<workspace_id>/architecture/decompose/
       Generate a non-persistent decomposition draft for an ArchitectureElement.
       Body: {element_id, breadth?, depth?}. Returns the draft for review.
       Nothing is written. 403 when the workspace is minimal-rigor.

  POST /api/v1/workspaces/<workspace_id>/architecture/decompose/commit/
       Persist a reviewed draft in one transaction. Body: {draft}. On success
       returns the created element/requirement/link ids and the verified rule
       set. A draft whose committed result violates ARCH-003/TRACE-P4/P5 is
       rolled back and returns 422 with the offending findings.

Module rationale: mirrors the dedicated-module convention (audit_views.py,
settings_views.py, ...) rather than growing views.py.
"""
from __future__ import annotations

from typing import Any

from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.architecture_decompose_service import (
    ArchitectureDecomposeService,
    DecompositionAuditError,
    DecompositionDraft,
    DecompositionNotAvailableError,
)
from application.base import NotFoundError, PermissionDeniedError, ValidationError
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import build_error_response, detect_lang


class GenerateDraftRequestSerializer(serializers.Serializer):
    """Body of POST .../architecture/decompose/."""

    element_id = serializers.UUIDField()
    breadth = serializers.IntegerField(required=False, min_value=1, max_value=5)
    depth = serializers.IntegerField(required=False, min_value=1, max_value=3)


class WorkspaceArchitectureDecomposeView(APIView):
    """POST .../architecture/decompose/ — generate a draft (no persistence)."""

    def post(
        self, request: Request, workspace_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        lang = detect_lang(request)
        ser = GenerateDraftRequestSerializer(data=request.data)
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
            draft = ArchitectureDecomposeService().generate_draft(
                get_auth_context(request),
                data["element_id"],
                max_breadth=data.get("breadth"),
                max_depth=data.get("depth"),
            )
            return Response(draft.to_dict(), status=status.HTTP_200_OK)
        except DecompositionNotAvailableError as exc:
            return Response(
                build_error_response("FEATURE_NOT_ENABLED", lang, message=str(exc)),
                status=status.HTTP_403_FORBIDDEN,
            )
        except NotFoundError as exc:
            return Response(
                build_error_response("NOT_FOUND", lang, message=str(exc)),
                status=status.HTTP_404_NOT_FOUND,
            )
        except ValidationError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except PermissionDeniedError as exc:
            return Response(
                build_error_response("PERMISSION_DENIED", lang, message=str(exc)),
                status=status.HTTP_403_FORBIDDEN,
            )
        except Exception:
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class WorkspaceArchitectureDecomposeCommitView(APIView):
    """POST .../architecture/decompose/commit/ — persist a reviewed draft."""

    def post(
        self, request: Request, workspace_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        lang = detect_lang(request)
        raw_draft = request.data.get("draft") if isinstance(request.data, dict) else None
        if not isinstance(raw_draft, dict):
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    message="Body must contain a 'draft' object.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            draft = DecompositionDraft.from_dict(raw_draft)
            result = ArchitectureDecomposeService().commit_draft(
                get_auth_context(request), draft
            )
            return Response(result.to_dict(), status=status.HTTP_201_CREATED)
        except DecompositionNotAvailableError as exc:
            return Response(
                build_error_response("FEATURE_NOT_ENABLED", lang, message=str(exc)),
                status=status.HTTP_403_FORBIDDEN,
            )
        except DecompositionAuditError as exc:
            # The committed graph failed SE-Auditor verification and was rolled
            # back — 422 with the offending findings so the UI can explain why.
            payload = build_error_response(
                "VALIDATION_ERROR", lang, message=str(exc)
            )
            payload["findings"] = exc.findings
            return Response(payload, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        except NotFoundError as exc:
            return Response(
                build_error_response("NOT_FOUND", lang, message=str(exc)),
                status=status.HTTP_404_NOT_FOUND,
            )
        except ValidationError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except PermissionDeniedError as exc:
            return Response(
                build_error_response("PERMISSION_DENIED", lang, message=str(exc)),
                status=status.HTTP_403_FORBIDDEN,
            )
        except Exception:
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


__all__ = [
    "WorkspaceArchitectureDecomposeView",
    "WorkspaceArchitectureDecomposeCommitView",
]
