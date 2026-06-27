"""
COMP-RA-001 HttpEndpointController — DRF ViewSets for all domain operations.

leaf_id : COMP-RA-001
req_id  : REQ-L2-RA-001 (CRUD endpoints), REQ-L2-RA-003 (performance),
          REQ-L2-RA-007 (audit-log delegation), REQ-L2-RA-009 (error format),
          REQ-L2-RA-012 (no business logic)
          REQ-L3-RA001-001 through REQ-L3-RA001-004

Architecture:
  docs/se/L1/Gesamtsystem/L2/RestApiAdapterSystem/Components/
    COMP-RA-001_HttpEndpointController/L3_COMP-RA-001_HttpEndpointController_Architecture.md

Interfaces:
  IF-RA-EXT-IN-001/002  <- HTTP requests from API clients / ReactFrontend
  IF-RA-EXT-OUT-001     -> JSON responses
  IF-RA-EXT-OUT-005     -> ApplicationService (single entry point, ADR-01)
  IF-RA-INT-001         -> COMP-RA-003 AuthEnforcer (via DRF auth classes in settings)
  IF-RA-INT-002         -> COMP-RA-004 PresetGuard (PresetGateMixin)
  IF-RA-INT-003         <-> COMP-RA-002 DataSerializer (serializers)

Design decisions:
  - DRF ViewSets per entity; DRF Router for URL registration.
  - No business logic in views (REQ-L3-RA001-004).
  - All ApplicationService exceptions mapped to HTTP codes without stack-trace leakage.
  - Audit context is passed through to ApplicationService via AuthContext
    (actor identity, operation type carried implicitly by service method).
  - Queryset optimized with select_related/prefetch_related (REQ-L2-RA-013).
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from django.http import Http404, HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.services import (
    ArtifactService,
    ArtifactDiffService,
    BaselineFacade,
    NotFoundError,
    PermissionDeniedError,
    RequirementService,
    ArchitectureService,
    SearchService,
    TestService,
    TestRunService,
    TraceLinkService,
    ValidationError,
    WorkflowFacade,
    WorkspaceService,
    ExportService,
    ImportService,
    AdrService,
    RiskService,
    IssueService,
)
from audit.query import AuditLogQuery, AuditQueryFilters
from rest_api.auth_enforcer import get_auth_context

logger = logging.getLogger(__name__)
from rest_api.preset_guard import PresetError, PresetGateMixin
from rest_api.serializers import (
    AdrSerializer,
    ArtifactSerializer,
    ArchitectureElementSerializer,
    BaselineSerializer,
    IssueSerializer,
    RequirementSerializer,
    RiskSerializer,
    StandardPagination,
    TestCaseSerializer,
    TestRunSerializer,
    TestRunResultSerializer,
    TraceLinkSerializer,
    WorkflowDefinitionSerializer,
    WorkspaceSerializer,
    build_error_response,
    detect_lang,
)

# ---------------------------------------------------------------------------
# Exception → HTTP status mapper (REQ-L3-RA001-002)
# No business logic — purely HTTP-concern translation.
# ---------------------------------------------------------------------------

_EXC_TO_HTTP: dict[type, int] = {
    ValidationError: status.HTTP_400_BAD_REQUEST,
    PermissionDeniedError: status.HTTP_403_FORBIDDEN,
    NotFoundError: status.HTTP_404_NOT_FOUND,
}

_EXC_TO_CODE: dict[type, str] = {
    ValidationError: "VALIDATION_ERROR",
    PermissionDeniedError: "PERMISSION_DENIED",
    NotFoundError: "NOT_FOUND",
}


def _service_error_response(exc: Exception, lang: str = "en") -> Response:
    """Translate an ApplicationService exception into a standardised error Response.

    REQ-L3-RA001-002: No stack traces leaked; uses ErrorResponseFormatter pattern.
    """
    exc_type = type(exc)
    http_status = _EXC_TO_HTTP.get(exc_type, status.HTTP_500_INTERNAL_SERVER_ERROR)
    code = _EXC_TO_CODE.get(exc_type, "INTERNAL_SERVER_ERROR")
    body = build_error_response(
        code=code,
        lang=lang,
        message=str(exc) or None,
    )
    return Response(body, status=http_status)


# ---------------------------------------------------------------------------
# Base ViewSet mixin: error handling + auth context
# REQ-L3-RA001-004: no business logic — only HTTP translation.
# ---------------------------------------------------------------------------


class BaseEntityViewSet(PresetGateMixin, viewsets.ViewSet):
    """Shared behaviour: error mapping, auth context, preset gate, pagination.

    Subclasses must implement list(), retrieve(), create(), partial_update(),
    destroy() and set:
      - serializer_class
      - preset_endpoint_key (optional, from PresetGateMixin)
    """

    serializer_class: type | None = None
    pagination_class = StandardPagination

    @property
    def paginator(self) -> StandardPagination:
        if not hasattr(self, "_paginator"):
            self._paginator = self.pagination_class()
        return self._paginator

    def _paginate(self, request: Request, data: list) -> Response:
        """Apply pagination to a list and return a paginated Response."""
        page = self.paginator.paginate_queryset(data, request, view=self)
        if page is not None:
            return self.paginator.get_paginated_response(page)
        return Response(data)

    def list(self, request: Request, **kwargs: Any) -> Response:
        raise NotImplementedError

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        raise NotImplementedError

    def create(self, request: Request, **kwargs: Any) -> Response:
        raise NotImplementedError

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        raise NotImplementedError

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# COMP-RA-001: RequirementViewSet
# REQ-L3-RA001-001: CRUD for Requirement entity
# ---------------------------------------------------------------------------


class RequirementViewSet(BaseEntityViewSet):
    """ViewSet for Requirement CRUD operations.

    Delegates to RequirementService (ApplicationService facade, ADR-01).
    No business logic in this class (REQ-L3-RA001-004).

    REQ-L2-RA-001: GET list, GET detail, POST, PATCH, DELETE.
    REQ-L2-RA-007: Audit context is passed through service methods.
    REQ-L2-RA-013: Queryset uses select_related (applied in service layer).
    """

    serializer_class = RequirementSerializer
    preset_endpoint_key = ""  # Requirements are always visible

    def _svc(self) -> RequirementService:
        return RequirementService()

    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/requirements/ — list all requirements."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id_str = request.query_params.get("workspace_id")
            if not workspace_id_str:
                return Response(
                    build_error_response("VALIDATION_ERROR", lang, message="workspace_id is required"),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            workspace_id = UUID(workspace_id_str)
            items = self._svc().list_requirements(workspace_id=workspace_id, ctx=ctx)
        except (ValidationError, ValueError) as exc:
            return _service_error_response(exc if isinstance(exc, ValidationError) else ValidationError(str(exc)), lang)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)

        serialized = [RequirementSerializer(_dto_from_orm(item)).data for item in items]
        return self._paginate(request, serialized)

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/requirements/{pk}/ — retrieve single requirement."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_requirement(UUID(pk), ctx)
        except NotFoundError as exc:
            return _service_error_response(exc, lang)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(RequirementSerializer(_dto_from_orm(item)).data)

    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/requirements/ — create a requirement. Returns 201."""
        lang = detect_lang(request)
        ser = RequirementSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = ser.validated_data
        try:
            ctx = get_auth_context(request)
            item = self._svc().create_requirement(
                workspace_id=UUID(str(data["workspace_id"])),
                title=data["title"],
                ctx=ctx,
                description=data.get("description", ""),
                category=data.get("category", ""),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(RequirementSerializer(_dto_from_orm(item)).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """PATCH /api/v1/requirements/{pk}/ — update a requirement. Returns 200."""
        lang = detect_lang(request)
        ser = RequirementSerializer(data=request.data, partial=True)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = ser.validated_data
        try:
            ctx = get_auth_context(request)
            item = self._svc().update_requirement(
                requirement_id=UUID(pk),
                ctx=ctx,
                title=data.get("title"),
                description=data.get("description"),
                category=data.get("category"),
                status=data.get("status"),
                change_reason=data.get("change_reason"),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(RequirementSerializer(_dto_from_orm(item)).data)

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/architecture/{pk}/ — delete an architecture element. Returns 204."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            self._svc().delete_architecture_element(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"], url_path="diff")
    def diff(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/architecture/{pk}/diff/?from_version=0&to_version=2

        REQ-L2-AS-032 / REQ-L1-040: Structured field-level diff.
        Delegates to ArtifactDiffService (COMP-AS-019).
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            el = self._svc().get_architecture_element(UUID(pk), ctx)
            artifact_id = el.artifact_id

            from_version = int(request.query_params.get("from_version", "0"))
            to_version = int(request.query_params.get("to_version", str(el.version)))

            diff_svc = ArtifactDiffService()
            result = diff_svc.diff(
                artifact_id=UUID(str(artifact_id)),
                from_version=from_version,
                to_version=to_version,
                ctx=ctx,
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(result)

    @action(detail=True, methods=["get"], url_path="versions")
    def versions(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/architecture/{pk}/versions/ — list available versions."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            el = self._svc().get_architecture_element(UUID(pk), ctx)
            artifact_id = el.artifact_id

            diff_svc = ArtifactDiffService()
            result = diff_svc.list_versions(
                artifact_id=UUID(str(artifact_id)),
                ctx=ctx,
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(result)

    @action(detail=True, methods=["get"], url_path="diff")
    def diff(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/requirements/{pk}/diff/?from_version=0&to_version=2

        REQ-L2-AS-032 / REQ-L1-040: Structured field-level diff.
        Delegates to ArtifactDiffService (COMP-AS-019).
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            # Resolve artifact_id from requirement
            req = self._svc().get_requirement(UUID(pk), ctx)
            artifact_id = req.artifact_id

            from_version = int(request.query_params.get("from_version", "0"))
            to_version = int(request.query_params.get("to_version", str(req.version)))

            diff_svc = ArtifactDiffService()
            result = diff_svc.diff(
                artifact_id=UUID(str(artifact_id)),
                from_version=from_version,
                to_version=to_version,
                ctx=ctx,
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(result)

    @action(detail=True, methods=["get"], url_path="versions")
    def versions(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/requirements/{pk}/versions/ — list available versions."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            req = self._svc().get_requirement(UUID(pk), ctx)
            artifact_id = req.artifact_id

            diff_svc = ArtifactDiffService()
            result = diff_svc.list_versions(
                artifact_id=UUID(str(artifact_id)),
                ctx=ctx,
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(result)


# ---------------------------------------------------------------------------
# RequirementHistoryView — REQ-L0-011: Audit-Trail for Requirements
# ---------------------------------------------------------------------------


class RequirementHistoryView(APIView):
    """GET /api/v1/requirements/{pk}/history/ — Audit-Trail für Requirements.

    REQ-L0-011: Returns paginated audit entries from the audit_entry table
    for a specific Requirement. Uses AuditLogQuery (COMP-AL-002) for
    filtered/paginated access with tenant isolation.

    Query params:
        page      — page number (default 1)
        page_size — entries per page (default 50, max 100)
    """

    def get(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            # Verify requirement exists and user has access (also sets tenant context)
            req_service = RequirementService()
            # pk is already a UUID object from Django <uuid:pk> URL converter
            req_pk = pk if isinstance(pk, UUID) else UUID(pk)
            req_service.get_requirement(req_pk, ctx)

            # Parse pagination params
            try:
                page = int(request.query_params.get("page", 1))
                page_size = int(request.query_params.get("page_size", 50))
            except (ValueError, TypeError):
                return Response(
                    build_error_response(
                        "VALIDATION_ERROR", lang,
                        message="page and page_size must be integers",
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Cap page_size to prevent excessive queries
            page_size = min(page_size, 100)

            # Query audit entries for this requirement
            filters = AuditQueryFilters(
                entity_id=req_pk,
                entity_type="Requirement",
            )
            result = AuditLogQuery.query(
                filters=filters,
                page=page,
                page_size=page_size,
            )

            return Response({
                "results": [
                    {
                        "id": str(e.id),
                        "actor": e.actor,
                        "actor_type": e.actor_type,
                        "operation": e.op,
                        "timestamp": e.timestamp.isoformat(),
                        "change_reason": e.change_reason,
                        "entity_version": e.entity_version,
                        "source": e.source,
                    }
                    for e in result.entries
                ],
                "total": result.total,
                "page": result.page,
                "page_size": result.page_size,
            })
        except (NotFoundError, PermissionDeniedError) as exc:
            logger.error("RequirementHistoryView: auth error %s", exc)
            return _service_error_response(exc, lang)
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            logger.exception("RequirementHistoryView: unhandled exception for pk=%s type(pk)=%s", pk, type(pk).__name__)
            return _service_error_response(exc, lang)


# ---------------------------------------------------------------------------
# ArtifactViewSet
# ---------------------------------------------------------------------------


class ArtifactViewSet(BaseEntityViewSet):
    """ViewSet for Artifact CRUD operations (REQ-L2-RA-001)."""

    serializer_class = ArtifactSerializer
    preset_endpoint_key = ""

    def _svc(self) -> ArtifactService:
        return ArtifactService()

    def list(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id_str = request.query_params.get("workspace_id")
            if not workspace_id_str:
                return Response(
                    build_error_response("VALIDATION_ERROR", lang, message="workspace_id is required"),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            self._svc()._set_tenant_context(ctx)
            from persistence.models import Artifact
            qs = Artifact.unscoped.filter(workspace_id=UUID(workspace_id_str)).values(
                "id", "parent_id", "artifact_type"
            )
            items = list(qs)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        serialized = [{"id": str(r["id"]), "parent_id": str(r["parent_id"]) if r["parent_id"] else None, "artifact_type": r["artifact_type"], "name": r.get("name", "")} for r in items]
        return self._paginate(request, serialized)

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_artifact(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(build_error_response("NOT_FOUND", lang), status=status.HTTP_404_NOT_FOUND)
        return Response(ArtifactSerializer(_artifact_to_dict(item)).data)

    def create(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ser = ArtifactSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                build_error_response("VALIDATION_ERROR", lang, details=[{"field": k, "errors": v} for k, v in ser.errors.items()]),
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = ser.validated_data
        try:
            ctx = get_auth_context(request)
            item = self._svc().create_artifact(
                workspace_id=UUID(str(data["workspace_id"])),
                artifact_type=data.get("artifact_type", "generic"),
                ctx=ctx,
                parent_id=data.get("parent_id"),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(ArtifactSerializer(_artifact_to_dict(item)).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ser = ArtifactSerializer(data=request.data, partial=True)
        if not ser.is_valid():
            return Response(
                build_error_response("VALIDATION_ERROR", lang, details=[{"field": k, "errors": v} for k, v in ser.errors.items()]),
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = ser.validated_data
        try:
            ctx = get_auth_context(request)
            item = self._svc().update_artifact(
                artifact_id=UUID(pk),
                ctx=ctx,
                artifact_type=data.get("artifact_type"),
                parent_id=data.get("parent_id"),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(ArtifactSerializer(_artifact_to_dict(item)).data)

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            self._svc().delete_artifact(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# ArchitectureElementViewSet
# ---------------------------------------------------------------------------


class ArchitectureElementViewSet(BaseEntityViewSet):
    """ViewSet for ArchitectureElement CRUD operations (REQ-L2-RA-001)."""

    serializer_class = ArchitectureElementSerializer
    preset_endpoint_key = ""

    def _svc(self) -> ArchitectureService:
        return ArchitectureService()

    def list(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id_str = request.query_params.get("workspace_id")
            if not workspace_id_str:
                return Response(build_error_response("VALIDATION_ERROR", lang, message="workspace_id is required"), status=status.HTTP_400_BAD_REQUEST)
            items = self._svc().list_architecture_elements(workspace_id=UUID(workspace_id_str), ctx=ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        serialized = [ArchitectureElementSerializer(_arch_to_dict(item)).data for item in items]
        return self._paginate(request, serialized)

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_architecture_element(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(build_error_response("NOT_FOUND", lang), status=status.HTTP_404_NOT_FOUND)
        return Response(ArchitectureElementSerializer(_arch_to_dict(item)).data)

    def create(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ser = ArchitectureElementSerializer(data=request.data)
        if not ser.is_valid():
            return Response(build_error_response("VALIDATION_ERROR", lang, details=[{"field": k, "errors": v} for k, v in ser.errors.items()]), status=status.HTTP_400_BAD_REQUEST)
        data = ser.validated_data
        try:
            ctx = get_auth_context(request)
            item = self._svc().create_architecture_element(workspace_id=UUID(str(data["workspace_id"])), title=data["title"], ctx=ctx, description=data.get("description", ""), element_type=data.get("element_type", ""))
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(ArchitectureElementSerializer(_arch_to_dict(item)).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ser = ArchitectureElementSerializer(data=request.data, partial=True)
        if not ser.is_valid():
            return Response(build_error_response("VALIDATION_ERROR", lang, details=[{"field": k, "errors": v} for k, v in ser.errors.items()]), status=status.HTTP_400_BAD_REQUEST)
        data = ser.validated_data
        try:
            ctx = get_auth_context(request)
            item = self._svc().update_architecture_element(arch_el_id=UUID(pk), ctx=ctx, title=data.get("title"), description=data.get("description"), element_type=data.get("element_type"))
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(ArchitectureElementSerializer(_arch_to_dict(item)).data)

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            self._svc().delete_architecture_element(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# TestCaseViewSet
# ---------------------------------------------------------------------------


class TestCaseViewSet(BaseEntityViewSet):
    """ViewSet for TestCase CRUD operations (REQ-L2-RA-001)."""

    serializer_class = TestCaseSerializer
    preset_endpoint_key = ""

    def _svc(self) -> TestService:
        return TestService()

    def list(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id_str = request.query_params.get("workspace_id")
            if not workspace_id_str:
                return Response(build_error_response("VALIDATION_ERROR", lang, message="workspace_id is required"), status=status.HTTP_400_BAD_REQUEST)
            items = self._svc().list_test_cases(workspace_id=UUID(workspace_id_str), ctx=ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        serialized = [TestCaseSerializer(_test_to_dict(item)).data for item in items]
        return self._paginate(request, serialized)

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_test_case(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(build_error_response("NOT_FOUND", lang), status=status.HTTP_404_NOT_FOUND)
        return Response(TestCaseSerializer(_test_to_dict(item)).data)

    def create(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ser = TestCaseSerializer(data=request.data)
        if not ser.is_valid():
            return Response(build_error_response("VALIDATION_ERROR", lang, details=[{"field": k, "errors": v} for k, v in ser.errors.items()]), status=status.HTTP_400_BAD_REQUEST)
        data = ser.validated_data
        try:
            ctx = get_auth_context(request)
            item = self._svc().create_test_case(workspace_id=UUID(str(data["workspace_id"])), title=data["title"], ctx=ctx, description=data.get("description", ""))
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(TestCaseSerializer(_test_to_dict(item)).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ser = TestCaseSerializer(data=request.data, partial=True)
        if not ser.is_valid():
            return Response(build_error_response("VALIDATION_ERROR", lang, details=[{"field": k, "errors": v} for k, v in ser.errors.items()]), status=status.HTTP_400_BAD_REQUEST)
        data = ser.validated_data
        try:
            ctx = get_auth_context(request)
            item = self._svc().update_test_case(test_case_id=UUID(pk), ctx=ctx, title=data.get("title"), description=data.get("description"))
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(TestCaseSerializer(_test_to_dict(item)).data)

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            self._svc().delete_test_case(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# TraceLinkViewSet
# ---------------------------------------------------------------------------


class TraceLinkViewSet(BaseEntityViewSet):
    """ViewSet for TraceLink CRUD operations (REQ-L2-RA-001)."""

    serializer_class = TraceLinkSerializer
    preset_endpoint_key = ""

    def _svc(self) -> TraceLinkService:
        return TraceLinkService()

    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/tracelinks/?workspace_id=<id>[&artifact_id=<id>]

        When artifact_id is provided: returns upstream + downstream links for that artifact.
        When only workspace_id is provided: returns empty list
        (workspace-level scan is not yet supported by TraceLinkService).
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id_str = request.query_params.get("workspace_id")
            if not workspace_id_str:
                return Response(
                    build_error_response("VALIDATION_ERROR", lang, message="workspace_id is required"),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            artifact_id_str = request.query_params.get("artifact_id")
            if not artifact_id_str:
                # Workspace-level listing not supported — return empty paginated result
                return self._paginate(request, [])

            artifact_id = UUID(artifact_id_str)
            svc = self._svc()
            items: list = []
            for direction in ("upstream", "downstream"):
                try:
                    results = svc.query_trace_links(
                        entity_id=artifact_id,
                        direction=direction,
                        ctx=ctx,
                    )
                    items.extend(results)
                except Exception:
                    pass  # no links in this direction — safe to ignore
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        serialized = [TraceLinkSerializer(_tracelink_to_dict(item)).data for item in items]
        return self._paginate(request, serialized)

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        # TraceLinkService does not have get_by_id — list and filter
        return Response(build_error_response("NOT_FOUND", lang), status=status.HTTP_404_NOT_FOUND)

    def create(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ser = TraceLinkSerializer(data=request.data)
        if not ser.is_valid():
            return Response(build_error_response("VALIDATION_ERROR", lang, details=[{"field": k, "errors": v} for k, v in ser.errors.items()]), status=status.HTTP_400_BAD_REQUEST)
        data = ser.validated_data
        try:
            ctx = get_auth_context(request)
            item = self._svc().create_trace_link(
                source_id=UUID(str(data["source_id"])),
                target_id=UUID(str(data["target_id"])),
                link_type=data["link_type"],
                ctx=ctx,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(TraceLinkSerializer(_tracelink_to_dict(item)).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        # TraceLinks are immutable (no update semantics in spec)
        return Response(
            build_error_response("VALIDATION_ERROR", detect_lang(request), message="TraceLinks cannot be updated. Delete and recreate."),
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            self._svc().cascade_delete_trace_links(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# BaselineViewSet (Extended-preset gate)
# ---------------------------------------------------------------------------


class BaselineViewSet(BaseEntityViewSet):
    """ViewSet for Baseline CRUD operations (REQ-L2-RA-001, REQ-L2-RA-008).

    Gated by preset: Baseline endpoints return 404 in Minimal preset.
    The preset gate raises Http404 and deliberately re-raises it past DRF's
    exception handler so callers (tests, middleware) receive the raw Django
    Http404 (REQ-L3-RA004-001).
    """

    serializer_class = BaselineSerializer
    preset_endpoint_key = "baselines"

    def _svc(self) -> BaselineFacade:
        return BaselineFacade()

    def handle_exception(self, exc: Exception) -> Response:
        """Re-raise Http404 so preset-gated 404s propagate past DRF.

        DRF normally converts Http404 to a Response; for preset-gated
        endpoints we want the raw Http404 to surface (REQ-L3-RA004-001).
        """
        if isinstance(exc, Http404):
            raise
        return super().handle_exception(exc)

    def _check_preset(self, request: Request) -> None:
        """Gate this endpoint by preset. Raises Http404 if not visible."""
        self.request = request
        self._guard_preset()

    def list(self, request: Request, **kwargs: Any) -> Response:
        self._check_preset(request)
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id_str = request.query_params.get("workspace_id")
            if not workspace_id_str:
                return Response(build_error_response("VALIDATION_ERROR", lang, message="workspace_id is required"), status=status.HTTP_400_BAD_REQUEST)
            items = self._svc().list_baselines(workspace_id=str(workspace_id_str), ctx=ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        serialized = [BaselineSerializer(_baseline_to_dict(item)).data for item in items]
        return self._paginate(request, serialized)

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        self._check_preset(request)
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_baseline(pk, ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(BaselineSerializer(_baseline_to_dict(item)).data)

    def create(self, request: Request, **kwargs: Any) -> Response:
        self._check_preset(request)
        lang = detect_lang(request)
        ser = BaselineSerializer(data=request.data)
        if not ser.is_valid():
            return Response(build_error_response("VALIDATION_ERROR", lang, details=[{"field": k, "errors": v} for k, v in ser.errors.items()]), status=status.HTTP_400_BAD_REQUEST)
        data = ser.validated_data
        try:
            ctx = get_auth_context(request)
            item = self._svc().create_baseline(
                workspace_id=str(data["workspace_id"]),
                artifact_id=str(data["artifact_id"]),
                scope=data.get("scope", "workspace"),
                ctx=ctx,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(BaselineSerializer(_baseline_to_dict(item)).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        # Baselines are immutable once created
        return Response(
            build_error_response("VALIDATION_ERROR", detect_lang(request), message="Baselines are immutable. Create a new baseline instead."),
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        # Baselines should not be deleted in normal operations
        return Response(
            build_error_response("PERMISSION_DENIED", detect_lang(request), message="Baselines cannot be deleted."),
            status=status.HTTP_403_FORBIDDEN,
        )


# ---------------------------------------------------------------------------
# WorkflowDefinitionViewSet
# ---------------------------------------------------------------------------


class WorkflowDefinitionViewSet(BaseEntityViewSet):
    """ViewSet for WorkflowDefinition CRUD operations (REQ-L2-RA-001)."""

    serializer_class = WorkflowDefinitionSerializer
    preset_endpoint_key = ""

    def _svc(self) -> WorkflowFacade:
        return WorkflowFacade()

    def list(self, request: Request, **kwargs: Any) -> Response:
        # WorkflowFacade does not expose list — return empty list
        return Response({"count": 0, "next": None, "previous": None, "results": []})

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        return Response(build_error_response("NOT_FOUND", detect_lang(request)), status=status.HTTP_404_NOT_FOUND)

    def create(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ser = WorkflowDefinitionSerializer(data=request.data)
        if not ser.is_valid():
            return Response(build_error_response("VALIDATION_ERROR", lang, details=[{"field": k, "errors": v} for k, v in ser.errors.items()]), status=status.HTTP_400_BAD_REQUEST)
        data = ser.validated_data
        try:
            ctx = get_auth_context(request)
            self._svc().initialize_workflow_states(
                item_ids=[data["artifact_id"]],
                item_type="Artifact",
                workspace_id=str(data["workspace_id"]),
                ctx=ctx,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response({"message": "Workflow initialized"}, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """Workflow transition via PATCH."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            target_state = request.data.get("target_state")
            change_reason = request.data.get("change_reason", "")
            if not target_state:
                return Response(build_error_response("VALIDATION_ERROR", lang, message="target_state is required"), status=status.HTTP_400_BAD_REQUEST)
            self._svc().transition(
                entity_id=UUID(pk),
                entity_type="Artifact",
                target_state=target_state,
                ctx=ctx,
                change_reason=change_reason,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response({"id": pk, "target_state": target_state})

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        return Response(build_error_response("PERMISSION_DENIED", detect_lang(request), message="Workflow definitions cannot be deleted."), status=status.HTTP_403_FORBIDDEN)


# ---------------------------------------------------------------------------
# DTO helper functions — ORM → dict for serializers
# Pure translation, no business logic (REQ-L3-RA001-004)
# ---------------------------------------------------------------------------


def _result_summary(test_run: Any) -> dict:
    """Compute result summary from a TestRun's results."""
    results = list(getattr(test_run, "_prefetched_results", test_run.results.all() if hasattr(test_run, "results") else []))
    total = len(results)
    passed = sum(1 for r in results if r.status == "passed")
    failed = sum(1 for r in results if r.status == "failed")
    blocked = sum(1 for r in results if r.status == "blocked")
    not_run = sum(1 for r in results if r.status == "not_run")
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "blocked": blocked,
        "not_run": not_run,
    }


def _test_run_to_dict(tr: Any) -> dict[str, Any]:
    """Convert TestRun ORM object to serializer-compatible dict."""
    return {
        "id": str(tr.id),
        "workspace_id": str(tr.workspace_id),
        "name": tr.name,
        "status": tr.status,
        "ci_job_id": getattr(tr, "ci_job_id", ""),
        "started_at": tr.started_at,
        "finished_at": tr.finished_at,
        "result_summary": _result_summary(tr),
        "version": tr.version,
        "created_at": tr.created_at,
        "updated_at": tr.modified_at,
    }


def _test_run_result_to_dict(r: Any) -> dict[str, Any]:
    """Convert TestRunResult ORM object to serializer-compatible dict."""
    return {
        "id": str(r.id),
        "test_run_id": str(r.test_run_id),
        "test_case_id": str(r.test_case_id) if r.test_case_id else None,
        "test_case_title": getattr(r, "test_case_title", ""),
        "status": r.status,
        "message": getattr(r, "message", ""),
        "duration_ms": getattr(r, "duration_ms", None),
        "executed_at": r.executed_at,
        "version": r.version,
        "created_at": r.created_at,
    }


def _dto_from_orm(req: Any) -> dict[str, Any]:
    """Convert Requirement ORM object to serializer-compatible dict."""
    return {
        "id": str(req.id),
        "workspace_id": str(req.artifact.workspace_id) if hasattr(req, "artifact") else None,
        "title": req.title,
        "description": getattr(req, "description", ""),
        "category": getattr(req, "category", ""),
        "status": getattr(req, "status", "draft"),
        "version": req.version,
        "created_at": req.created_at,
        "updated_at": req.modified_at,
    }


def _tree_node_to_dict(node: Any) -> dict[str, Any]:
    """Convert TreeNodeDTO to dict."""
    if hasattr(node, "as_dict"):
        return node.as_dict()
    return {
        "id": str(getattr(node, "id", "")),
        "artifact_type": getattr(node, "artifact_type", ""),
        "workspace_id": str(getattr(node, "workspace_id", "")),
        "parent_id": str(getattr(node, "parent_id", "")) if getattr(node, "parent_id", None) else None,
    }


def _artifact_to_dict(art: Any) -> dict[str, Any]:
    """Convert Artifact ORM object to dict."""
    return {
        "id": str(art.id),
        "workspace_id": str(art.workspace_id) if hasattr(art, "workspace_id") else None,
        "artifact_type": getattr(art, "artifact_type", ""),
        "parent_id": str(art.parent_id) if getattr(art, "parent_id", None) else None,
        "version": art.version,
        "created_at": art.created_at,
        "updated_at": art.modified_at,
    }


def _arch_to_dict(el: Any) -> dict[str, Any]:
    """Convert ArchitectureElement ORM object to dict."""
    return {
        "id": str(el.id),
        "workspace_id": str(el.artifact.workspace_id) if hasattr(el, "artifact") else None,
        "title": el.title,
        "description": getattr(el, "description", ""),
        "element_type": getattr(el, "element_type", ""),
        "version": el.version,
        "created_at": el.created_at,
        "updated_at": el.modified_at,
    }


def _test_to_dict(tc: Any) -> dict[str, Any]:
    """Convert TestCase ORM object to dict."""
    return {
        "id": str(tc.id),
        "workspace_id": str(tc.artifact.workspace_id) if hasattr(tc, "artifact") else None,
        "title": tc.title,
        "description": getattr(tc, "description", ""),
        "status": getattr(tc, "status", "draft"),
        "version": tc.version,
        "created_at": tc.created_at,
        "updated_at": tc.modified_at,
    }


def _tracelink_to_dict(tl: Any) -> dict[str, Any]:
    """Convert TraceLink ORM object to dict."""
    return {
        "id": str(tl.id),
        "source_id": str(tl.source_id),
        "target_id": str(tl.target_id),
        "link_type": tl.link_type,
        "version": tl.version,
        "created_at": tl.created_at,
    }


def _baseline_to_dict(bl: Any) -> dict[str, Any]:
    """Convert Baseline ORM object to dict."""
    return {
        "id": str(bl.id),
        "workspace_id": str(bl.artifact.workspace_id) if hasattr(bl, "artifact") else None,
        "artifact_id": str(bl.artifact_id),
        "scope": getattr(bl, "scope", ""),
        "version": bl.version,
        "created_at": bl.created_at,
    }


def _workspace_to_dict(ws: Any) -> dict[str, Any]:
    """Convert Workspace ORM object to serializer-compatible dict.

    ``terminology_profile`` is resolved from the optional
    ``WorkspacePresetConfig`` companion (defaults to ``"se_mode"`` when no
    preset config has been provisioned yet).
    """
    terminology_profile = "se_mode"
    preset_config = getattr(ws, "preset_config", None)
    if preset_config is not None:
        terminology_profile = getattr(
            preset_config, "terminology_profile", terminology_profile
        )
    return {
        "id": str(ws.id),
        "name": ws.name,
        "preset": ws.preset or {},
        "terminology_profile": terminology_profile,
        "language": "en",
        "version": ws.version,
        "created_at": ws.created_at,
        "updated_at": ws.modified_at,
    }


def _adr_to_dict(adr: Any) -> dict[str, Any]:
    """Convert Adr ORM object to serializer-compatible dict."""
    return {
        "id": str(adr.id),
        "workspace_id": str(adr.workspace_id),
        "title": adr.title,
        "description": getattr(adr, "description", ""),
        "context": getattr(adr, "context", ""),
        "consequences": getattr(adr, "consequences", ""),
        "status": getattr(adr, "status", "Draft"),
        "version": adr.version,
        "created_at": adr.created_at,
        "updated_at": adr.updated_at,
    }


def _risk_to_dict(risk: Any) -> dict[str, Any]:
    """Convert Risk ORM object to serializer-compatible dict."""
    return {
        "id": str(risk.id),
        "workspace_id": str(risk.workspace_id),
        "title": risk.title,
        "description": getattr(risk, "description", ""),
        "probability": getattr(risk, "probability", "low"),
        "impact": getattr(risk, "impact", "low"),
        "risk_score": getattr(risk, "risk_score", 1),
        "severity": getattr(risk, "severity", "low"),
        "category": getattr(risk, "category", "technical"),
        "owner": getattr(risk, "owner", ""),
        "mitigation_strategy": getattr(risk, "mitigation_strategy", ""),
        "status": getattr(risk, "status", "Identified"),
        "version": risk.version,
        "created_at": risk.created_at,
        "updated_at": risk.updated_at,
    }


def _issue_to_dict(issue: Any) -> dict[str, Any]:
    """Convert Issue ORM object to serializer-compatible dict."""
    return {
        "id": str(issue.id),
        "workspace_id": str(issue.workspace_id),
        "title": issue.title,
        "description": getattr(issue, "description", ""),
        "severity": getattr(issue, "severity", "medium"),
        "category": getattr(issue, "category", "defect"),
        "status": getattr(issue, "status", "Open"),
        "tags": issue.tags if isinstance(issue.tags, list) else [],
        "created_at": issue.created_at,
        "updated_at": issue.updated_at,
    }


# ---------------------------------------------------------------------------
# WorkspaceViewSet (read-only — list + retrieve, REQ-L1-017)
# ---------------------------------------------------------------------------


class WorkspaceViewSet(BaseEntityViewSet):
    """ViewSet for Workspace lookup (REQ-L1-017).

    Read-only surface: workspaces are provisioned via seeding / admin tooling
    today. ``list`` returns all workspaces of the active tenant; ``retrieve``
    fetches a single workspace by id. Tenant scoping is enforced by
    WorkspaceService via TenantContext.
    """

    serializer_class = WorkspaceSerializer
    preset_endpoint_key = ""  # Workspaces are always visible

    def _svc(self) -> WorkspaceService:
        return WorkspaceService()

    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/workspaces/ — list workspaces in the active tenant."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            items = self._svc().list_workspaces(ctx=ctx)
        except (ValidationError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        serialized = [WorkspaceSerializer(_workspace_to_dict(item)).data for item in items]
        return self._paginate(request, serialized)

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/workspaces/{pk}/ — fetch a single workspace by id."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_workspace(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(WorkspaceSerializer(_workspace_to_dict(item)).data)

    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/workspaces/ — create a new workspace + preset config.

        Body: {name, preset?, terminology_profile?, language?}
        Returns: 201 Created with the serialized Workspace.
        """
        lang = detect_lang(request)
        name = request.data.get("name")
        if not name or not str(name).strip():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message="name is required"
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        preset = request.data.get("preset", "standard")
        terminology_profile = request.data.get("terminology_profile", "se_mode")
        language = request.data.get("language", "de")
        try:
            ctx = get_auth_context(request)
            item = self._svc().create_workspace(
                ctx=ctx,
                name=str(name),
                preset=str(preset),
                terminology_profile=str(terminology_profile),
                language=str(language),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(
            WorkspaceSerializer(_workspace_to_dict(item)).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request: Request, pk: str = None, **kwargs: Any) -> Response:
        """PATCH /api/v1/workspaces/{pk}/ — update workspace metadata.

        Body: {name?, language?, terminology_profile?}
        REQ-L2-RF-012: Workspace-Konfigurations-UI write path.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            from persistence.models import Workspace
            self._svc()._set_tenant_context(ctx)
            ws = Workspace.objects.filter(id=pk).first()
            if ws is None:
                return Response(
                    build_error_response("NOT_FOUND", lang),
                    status=status.HTTP_404_NOT_FOUND,
                )

            update_fields: list[str] = []
            preset_blob = dict(ws.preset or {})

            if "name" in request.data:
                new_name = str(request.data.get("name") or "").strip()
                if not new_name:
                    return Response(
                        build_error_response(
                            "VALIDATION_ERROR", lang, message="name must not be empty"
                        ),
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                ws.name = new_name
                update_fields.append("name")

            if "language" in request.data:
                preset_blob["language"] = str(request.data["language"])
                ws.preset = preset_blob
                if "preset" not in update_fields:
                    update_fields.append("preset")

            if "terminology_profile" in request.data:
                target_profile = str(request.data["terminology_profile"])
                if target_profile not in ("dev_mode", "se_mode"):
                    return Response(
                        build_error_response(
                            "VALIDATION_ERROR",
                            lang,
                            message="terminology_profile must be dev_mode or se_mode",
                        ),
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                from presets.services import switch_terminology_profile
                switch_terminology_profile(
                    workspace_id=str(pk), target_profile=target_profile
                )
                preset_blob["terminology_profile"] = target_profile
                ws.preset = preset_blob
                if "preset" not in update_fields:
                    update_fields.append("preset")

            if update_fields:
                ws.save(update_fields=update_fields)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(WorkspaceSerializer(_workspace_to_dict(ws)).data)

    @action(detail=True, methods=["patch"], url_path="preset")
    def set_preset(self, request: Request, pk: str = None, **kwargs: Any) -> Response:
        """PATCH /api/v1/workspaces/{pk}/preset/ — switch active preset tier.

        Body: {preset: "minimal" | "standard" | "extended"}
        REQ-L2-RF-007 / REQ-L2-RF-012: Preset switch from Workspace Settings UI.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            target_tier = request.data.get("preset")
            if not target_tier or target_tier not in (
                "minimal",
                "standard",
                "extended",
            ):
                return Response(
                    build_error_response(
                        "VALIDATION_ERROR",
                        lang,
                        message="preset must be minimal, standard or extended",
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            from presets.services import switch_preset
            switch_preset(workspace_id=str(pk), target_preset=str(target_tier))
            from persistence.models import Workspace
            self._svc()._set_tenant_context(ctx)
            ws = Workspace.objects.filter(id=pk).first()
            if ws is None:
                return Response(
                    build_error_response("NOT_FOUND", lang),
                    status=status.HTTP_404_NOT_FOUND,
                )
            preset_blob = dict(ws.preset or {})
            preset_blob["tier"] = target_tier
            preset_blob["name"] = target_tier
            ws.preset = preset_blob
            ws.save(update_fields=["preset"])
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response({"id": str(pk), "preset": target_tier})

    @action(detail=True, methods=["get"], url_path="reports/pdf")
    def report_pdf(self, request: Request, pk: str = None, **kwargs: Any) -> HttpResponse:
        """GET /api/v1/workspaces/{pk}/reports/pdf/?layout=...

        REQ-L2-AS-016 / REQ-L1-023: Generate a PDF report for the workspace.

        Query params:
            layout: "requirement_document" (default) | "traceability_matrix"

        Returns:
            application/pdf response with Content-Disposition header.
        """
        lang = detect_lang(request)
        layout = request.query_params.get("layout", "requirement_document")

        try:
            ctx = get_auth_context(request)
            # Verify workspace exists and user has access
            ws = self._svc().get_workspace(UUID(pk), ctx)

            from traceability.pdf_report_generator import generate_pdf_report

            pdf_bytes = generate_pdf_report(
                workspace_id=UUID(pk),
                layout=layout,
                ctx=ctx,
            )
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)

        ws_name = ws.name.replace(" ", "_")
        filename = f"{ws_name}_{layout}.pdf"

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


# ---------------------------------------------------------------------------
# AdrViewSet — COMP-AS-013 (REQ-L1-029)
# ---------------------------------------------------------------------------


class AdrViewSet(BaseEntityViewSet):
    """ViewSet for ADR CRUD operations (REQ-L1-029).

    Delegates to AdrService (COMP-AS-013, ADR-01).
    No business logic in this class (REQ-L3-RA001-004).
    """

    serializer_class = AdrSerializer
    preset_endpoint_key = ""

    def _svc(self) -> AdrService:
        return AdrService()

    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/adrs/ — list all ADRs in a workspace."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id_str = request.query_params.get("workspace_id")
            if not workspace_id_str:
                return Response(
                    build_error_response("VALIDATION_ERROR", lang, message="workspace_id is required"),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            workspace_id = UUID(workspace_id_str)
            items = self._svc().list_adrs(workspace_id=workspace_id, ctx=ctx)
        except (ValidationError, ValueError) as exc:
            return _service_error_response(exc if isinstance(exc, ValidationError) else ValidationError(str(exc)), lang)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        serialized = [AdrSerializer(_adr_to_dict(item)).data for item in items]
        return self._paginate(request, serialized)

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/adrs/{pk}/ — retrieve single ADR."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_adr(UUID(pk), ctx)
        except NotFoundError as exc:
            return _service_error_response(exc, lang)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(AdrSerializer(_adr_to_dict(item)).data)

    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/adrs/ — create an ADR. Returns 201."""
        lang = detect_lang(request)
        ser = AdrSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = ser.validated_data
        try:
            ctx = get_auth_context(request)
            item = self._svc().create_adr(
                workspace_id=UUID(str(data["workspace_id"])),
                title=data["title"],
                description=data.get("description", ""),
                ctx=ctx,
                context=data.get("context", ""),
                consequences=data.get("consequences", ""),
                status=data.get("status", "Draft"),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(AdrSerializer(_adr_to_dict(item)).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """PATCH /api/v1/adrs/{pk}/ — update an ADR. Returns 200."""
        lang = detect_lang(request)
        ser = AdrSerializer(data=request.data, partial=True)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = ser.validated_data
        try:
            ctx = get_auth_context(request)
            item = self._svc().update_adr(
                adr_id=UUID(pk),
                ctx=ctx,
                title=data.get("title"),
                description=data.get("description"),
                context=data.get("context"),
                consequences=data.get("consequences"),
                change_reason=data.get("change_reason"),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(AdrSerializer(_adr_to_dict(item)).data)

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/adrs/{pk}/ — delete an ADR. Returns 204."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            self._svc().delete_adr(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# RiskViewSet — COMP-AS-014 (REQ-L1-029)
# ---------------------------------------------------------------------------


class RiskViewSet(BaseEntityViewSet):
    """ViewSet for Risk CRUD operations (REQ-L1-029).

    Delegates to RiskService (COMP-AS-014, ADR-01).
    No business logic in this class (REQ-L3-RA001-004).
    """

    serializer_class = RiskSerializer
    preset_endpoint_key = ""

    def _svc(self) -> RiskService:
        return RiskService()

    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/risks/ — list all Risks in a workspace."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id_str = request.query_params.get("workspace_id")
            if not workspace_id_str:
                return Response(
                    build_error_response("VALIDATION_ERROR", lang, message="workspace_id is required"),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            workspace_id = UUID(workspace_id_str)
            items = self._svc().list_risks(workspace_id=workspace_id, ctx=ctx)
        except (ValidationError, ValueError) as exc:
            return _service_error_response(exc if isinstance(exc, ValidationError) else ValidationError(str(exc)), lang)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        serialized = [RiskSerializer(_risk_to_dict(item)).data for item in items]
        return self._paginate(request, serialized)

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/risks/{pk}/ — retrieve single Risk."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_risk(UUID(pk), ctx)
        except NotFoundError as exc:
            return _service_error_response(exc, lang)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(RiskSerializer(_risk_to_dict(item)).data)

    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/risks/ — create a Risk. Returns 201."""
        lang = detect_lang(request)
        ser = RiskSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = ser.validated_data
        try:
            ctx = get_auth_context(request)
            item = self._svc().create_risk(
                workspace_id=UUID(str(data["workspace_id"])),
                title=data["title"],
                probability=data.get("probability", "medium"),
                impact=data.get("impact", "medium"),
                ctx=ctx,
                description=data.get("description", ""),
                category=data.get("category", "technical"),
                owner=data.get("owner", ""),
                mitigation_strategy=data.get("mitigation_strategy", ""),
                status=data.get("status", "Identified"),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(RiskSerializer(_risk_to_dict(item)).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """PATCH /api/v1/risks/{pk}/ — update a Risk. Returns 200."""
        lang = detect_lang(request)
        ser = RiskSerializer(data=request.data, partial=True)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = ser.validated_data
        try:
            ctx = get_auth_context(request)
            item = self._svc().update_risk(
                risk_id=UUID(pk),
                ctx=ctx,
                title=data.get("title"),
                description=data.get("description"),
                probability=data.get("probability"),
                impact=data.get("impact"),
                category=data.get("category"),
                owner=data.get("owner"),
                mitigation_strategy=data.get("mitigation_strategy"),
                change_reason=data.get("change_reason"),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(RiskSerializer(_risk_to_dict(item)).data)

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/risks/{pk}/ — delete a Risk. Returns 204."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            self._svc().delete_risk(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# IssueViewSet — COMP-AS-015 (REQ-L1-029)
# ---------------------------------------------------------------------------


class IssueViewSet(BaseEntityViewSet):
    """ViewSet for Issue CRUD operations (REQ-L1-029).

    Delegates to IssueService (COMP-AS-015, ADR-01).
    No business logic in this class (REQ-L3-RA001-004).
    """

    serializer_class = IssueSerializer
    preset_endpoint_key = ""

    def _svc(self) -> IssueService:
        return IssueService()

    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/issues/ — list all Issues in a workspace."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id_str = request.query_params.get("workspace_id")
            if not workspace_id_str:
                return Response(
                    build_error_response("VALIDATION_ERROR", lang, message="workspace_id is required"),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            workspace_id = UUID(workspace_id_str)
            items = self._svc().list_issues(workspace_id=workspace_id, ctx=ctx)
        except (ValidationError, ValueError) as exc:
            return _service_error_response(exc if isinstance(exc, ValidationError) else ValidationError(str(exc)), lang)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        serialized = [IssueSerializer(_issue_to_dict(item)).data for item in items]
        return self._paginate(request, serialized)

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/issues/{pk}/ — retrieve single Issue."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_issue(UUID(pk), ctx)
        except NotFoundError as exc:
            return _service_error_response(exc, lang)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(IssueSerializer(_issue_to_dict(item)).data)

    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/issues/ — create an Issue. Returns 201."""
        lang = detect_lang(request)
        ser = IssueSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = ser.validated_data
        try:
            ctx = get_auth_context(request)
            item = self._svc().create_issue(
                workspace_id=UUID(str(data["workspace_id"])),
                title=data["title"],
                severity=data.get("severity", "medium"),
                ctx=ctx,
                description=data.get("description", ""),
                category=data.get("category", "defect"),
                tags=data.get("tags"),
                status=data.get("status", "Open"),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(IssueSerializer(_issue_to_dict(item)).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """PATCH /api/v1/issues/{pk}/ — update an Issue. Returns 200."""
        lang = detect_lang(request)
        ser = IssueSerializer(data=request.data, partial=True)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = ser.validated_data
        try:
            ctx = get_auth_context(request)
            item = self._svc().update_issue(
                issue_id=UUID(pk),
                ctx=ctx,
                title=data.get("title"),
                description=data.get("description"),
                severity=data.get("severity"),
                category=data.get("category"),
                tags=data.get("tags"),
                change_reason=data.get("change_reason"),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(IssueSerializer(_issue_to_dict(item)).data)

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/testcases/{pk}/ — delete a test case. Returns 204."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            self._svc().delete_test_case(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"], url_path="diff")
    def diff(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/testcases/{pk}/diff/?from_version=0&to_version=2

        REQ-L2-AS-032 / REQ-L1-040: Structured field-level diff.
        Delegates to ArtifactDiffService (COMP-AS-019).
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            tc = self._svc().get_test_case(UUID(pk), ctx)
            artifact_id = tc.artifact_id

            from_version = int(request.query_params.get("from_version", "0"))
            to_version = int(request.query_params.get("to_version", str(tc.version)))

            diff_svc = ArtifactDiffService()
            result = diff_svc.diff(
                artifact_id=UUID(str(artifact_id)),
                from_version=from_version,
                to_version=to_version,
                ctx=ctx,
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(result)


# ---------------------------------------------------------------------------
# TestRunViewSet — REQ-L2-AS-030 / REQ-L2-AS-031
# ---------------------------------------------------------------------------


class TestRunViewSet(BaseEntityViewSet):
    """ViewSet for TestRun CRUD and result management.

    Endpoints:
      GET    /api/v1/test-runs/?workspace_id=<id>
      POST   /api/v1/test-runs/
      GET    /api/v1/test-runs/{id}/
      PATCH  /api/v1/test-runs/{id}/
      POST   /api/v1/test-runs/{id}/close/
      POST   /api/v1/test-runs/{id}/results/
      POST   /api/v1/test-runs/{id}/results/bulk/
    """

    serializer_class = TestRunSerializer
    preset_endpoint_key = ""

    def _svc(self) -> TestRunService:
        return TestRunService()

    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/test-runs/?workspace_id=<id> — list test runs."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id_str = request.query_params.get("workspace_id")
            if not workspace_id_str:
                return Response(
                    build_error_response("VALIDATION_ERROR", lang, message="workspace_id is required"),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            items = self._svc().list_test_runs(workspace_id=UUID(workspace_id_str), ctx=ctx)
        except (ValidationError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        serialized = [_test_run_to_dict(item) for item in items]
        return self._paginate(request, serialized)

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/test-runs/{id}/ — retrieve single test run."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().get_test_run(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except ValueError:
            return Response(build_error_response("NOT_FOUND", lang), status=status.HTTP_404_NOT_FOUND)
        return Response(_test_run_to_dict(item))

    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/test-runs/ — create a test run. Returns 201."""
        lang = detect_lang(request)
        workspace_id = request.data.get("workspace_id")
        name = request.data.get("name")
        if not workspace_id or not name:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="workspace_id and name are required"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ctx = get_auth_context(request)
            item = self._svc().create_test_run(
                workspace_id=UUID(str(workspace_id)),
                name=str(name),
                ctx=ctx,
                ci_job_id=str(request.data.get("ci_job_id", "")),
                test_case_ids=[UUID(str(tc_id)) for tc_id in request.data.get("test_case_ids", [])],
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(_test_run_to_dict(item), status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """PATCH /api/v1/test-runs/{id}/ — update test run metadata. Returns 200."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().update_test_run(
                test_run_id=UUID(pk),
                ctx=ctx,
                name=request.data.get("name"),
                ci_job_id=request.data.get("ci_job_id"),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(_test_run_to_dict(item))

    # ---- Actions ----

    @action(detail=True, methods=["post"])
    def close(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/test-runs/{id}/close/ — close test run, recalc aggregate."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item = self._svc().close_test_run(test_run_id=UUID(pk), ctx=ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(_test_run_to_dict(item))

    @action(detail=True, methods=["post"])
    def results(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/test-runs/{id}/results/ — add single result."""
        lang = detect_lang(request)
        test_case_id = request.data.get("test_case_id")
        status_val = request.data.get("status", "not_run")
        if not test_case_id:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="test_case_id is required"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ctx = get_auth_context(request)
            result = self._svc().add_result(
                test_run_id=UUID(pk),
                test_case_id=UUID(str(test_case_id)),
                status=str(status_val),
                ctx=ctx,
                message=str(request.data.get("message", "")),
                duration_ms=request.data.get("duration_ms"),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(_test_run_result_to_dict(result), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="results/bulk")
    def results_bulk(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/test-runs/{id}/results/bulk/ — add multiple results (CI-friendly)."""
        lang = detect_lang(request)
        results_data = request.data.get("results", [])
        if not results_data or not isinstance(results_data, list):
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="results array is required"),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ctx = get_auth_context(request)
            created = self._svc().add_results_bulk(
                test_run_id=UUID(pk),
                results=results_data,
                ctx=ctx,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(
            {"results": [_test_run_result_to_dict(r) for r in created], "count": len(created)},
            status=status.HTTP_201_CREATED,
        )

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/test-runs/{id}/ — not supported (immutable)."""
        return Response(
            build_error_response("PERMISSION_DENIED", detect_lang(request), message="Test runs cannot be deleted."),
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


# ---------------------------------------------------------------------------
# SearchViewSet — Full-text search across Requirements, ArchitectureElements,
# and TestCases (COMP-AS-010 SearchService).
# REQ-L1-020, REQ-L3-SEARCH-001 through REQ-L3-SEARCH-009
# ---------------------------------------------------------------------------


class SearchViewSet(viewsets.ViewSet):
    """ViewSet for full-text search.

    Delegates to SearchService (COMP-AS-010, ADR-01).
    No business logic in this class (REQ-L3-RA001-004).

    GET /api/v1/search/?q=<query>&workspace_id=<id>[&type=Requirement&page=1&limit=20]
    """

    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/search/ — full-text search.

        Query params:
          q             — search query (required)
          workspace_id  — workspace UUID (required)
          type          — optional type filter (Requirement|ArchitectureElement|TestCase)
                          may be repeated
          page          — page number (default 1)
          limit         — page size (default 20, max 100)
        """
        lang = detect_lang(request)
        query = request.query_params.get("q", "").strip()
        workspace_id_str = request.query_params.get("workspace_id")

        # Empty query or missing workspace → return empty result without error
        if not query or not workspace_id_str:
            return Response(
                {
                    "results": [],
                    "total_count": 0,
                    "page": 1,
                    "limit": 20,
                    "query": query,
                }
            )

        try:
            workspace_id = UUID(workspace_id_str)
        except ValueError:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message="workspace_id must be a UUID"
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse type filter (may be repeated)
        type_filter = request.query_params.getlist("type") or None

        # Parse pagination
        try:
            page = int(request.query_params.get("page", "1"))
            limit = int(request.query_params.get("limit", "20"))
        except ValueError:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message="page and limit must be integers"
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            ctx = get_auth_context(request)
            result = SearchService().search(
                query=query,
                ctx=ctx,
                workspace_id=workspace_id,
                type_filter=type_filter,
                page=page,
                limit=limit,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)

        # Serialize SearchHit dataclasses to dicts
        serialized_hits = [
            {
                "id": hit.id,
                "artifact_type": hit.artifact_type,
                "title": hit.title,
                "description": hit.description,
                "relevance_score": hit.relevance_score,
                "workspace_id": hit.workspace_id,
            }
            for hit in result.results
        ]
        return Response(
            {
                "results": serialized_hits,
                "total_count": result.total_count,
                "page": result.page,
                "limit": result.limit,
                "query": result.query,
            }
        )


# ---------------------------------------------------------------------------
# CsvImportView — COMP-AS-009 REST facade (REQ-L0-013, REQ-L2-AS-014)
# ---------------------------------------------------------------------------


class CsvImportView(APIView):
    """POST /api/v1/workspaces/{id}/import/csv/ — Bulk CSV import.

    REQ-L0-013: Effiziente Übernahme bestehender Anforderungsdaten.
    REQ-L2-AS-014: CSV Bulk Import (ApplicationService layer).
    REQ-L2-RF-016: Frontend CSV import UI.

    Body: multipart/form-data with:
        - ``file``: CSV file (RFC 4180, UTF-8).
        - ``entity_type``: "Requirement" | "ArchitectureElement" | "TestCase"

    Returns:
        201 with ImportResult summary on success.
        400 with validation errors (missing file, bad entity_type, malformed CSV,
        row limit exceeded, per-row validation failures).
    """

    _VALID_ENTITY_TYPES = {"Requirement", "ArchitectureElement", "TestCase"}

    def post(self, request: Request, pk: str = None, **kwargs: Any) -> Response:
        """Handle CSV import POST request."""
        lang = detect_lang(request)

        # --- Validate workspace param ---
        if not pk:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message="Workspace ID is required"),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            ctx = get_auth_context(request)
        except Exception as exc:
            return _service_error_response(exc, lang)

        # --- Validate entity_type ---
        entity_type = request.data.get("entity_type")
        if not entity_type:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang,
                    message="entity_type is required. Allowed: Requirement, ArchitectureElement, TestCase",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        if entity_type not in self._VALID_ENTITY_TYPES:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang,
                    message=f"Unsupported entity_type '{entity_type}'. Allowed: {sorted(self._VALID_ENTITY_TYPES)}",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- Validate file ---
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang,
                    message="No CSV file uploaded. Provide a 'file' field in multipart/form-data.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Read file content (UTF-8)
        try:
            csv_text = uploaded_file.read().decode("utf-8")
        except UnicodeDecodeError:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang,
                    message="CSV file must be UTF-8 encoded.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not csv_text.strip():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang,
                    message="CSV file is empty.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- Delegate to ImportService ---
        try:
            svc = ImportService()
            result = svc.import_csv(
                csv_text=csv_text,
                entity_type=entity_type,
                workspace_id=pk,
                ctx=ctx,
            )
        except ValidationError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except NotFoundError as exc:
            return _service_error_response(exc, lang)
        except PermissionDeniedError as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            logger.exception("CsvImportView: unhandled exception")
            return _service_error_response(exc, lang)

        # --- Build response ---
        response_data = {
            "success": result.success,
            "imported_count": result.imported_count,
            "skipped_count": result.skipped_count,
            "status": result.status,
            "errors": [
                {
                    "row_number": e.row_number,
                    "field": e.field,
                    "message": e.message,
                }
                for e in result.errors
            ],
        }

        http_status = status.HTTP_201_CREATED if result.success else status.HTTP_400_BAD_REQUEST
        return Response(response_data, status=http_status)


__all__ = [
    "RequirementViewSet",
    "ArtifactViewSet",
    "ArchitectureElementViewSet",
    "TestCaseViewSet",
    "TraceLinkViewSet",
    "BaselineViewSet",
    "WorkflowDefinitionViewSet",
    "WorkspaceViewSet",
    "AdrViewSet",
    "RiskViewSet",
    "IssueViewSet",
    "SearchViewSet",
    "CsvImportView",
    "ArtifactDiffService",
]
