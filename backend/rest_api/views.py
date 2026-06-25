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

from typing import Any
from uuid import UUID

from django.http import Http404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from application.services import (
    ArtifactService,
    BaselineFacade,
    NotFoundError,
    PermissionDeniedError,
    RequirementService,
    ArchitectureService,
    SearchService,
    TestService,
    TraceLinkService,
    ValidationError,
    WorkflowFacade,
    ExportService,
    ImportService,
    AdrService,
    RiskService,
    IssueService,
)
from rest_api.auth_enforcer import get_auth_context
from rest_api.preset_guard import PresetError, PresetGateMixin
from rest_api.serializers import (
    ArtifactSerializer,
    ArchitectureElementSerializer,
    BaselineSerializer,
    RequirementSerializer,
    StandardPagination,
    TestCaseSerializer,
    TraceLinkSerializer,
    WorkflowDefinitionSerializer,
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
                change_reason=data.get("change_reason"),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(RequirementSerializer(_dto_from_orm(item)).data)

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/requirements/{pk}/ — delete a requirement. Returns 204."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            self._svc().delete_requirement(UUID(pk), ctx)
        except (NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)


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
            items = self._svc().get_tree(UUID(workspace_id_str), ctx)
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            return _service_error_response(exc, lang)
        except Exception as exc:
            return _service_error_response(exc, lang)
        # get_tree returns TreeNodeDTO — serialize directly
        serialized = [_tree_node_to_dict(item) for item in items]
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
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id_str = request.query_params.get("workspace_id")
            if not workspace_id_str:
                return Response(build_error_response("VALIDATION_ERROR", lang, message="workspace_id is required"), status=status.HTTP_400_BAD_REQUEST)
            items = self._svc().query_trace_links(workspace_id=UUID(workspace_id_str), ctx=ctx)
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
    preset_endpoint_key = "baseline_endpoints"

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


__all__ = [
    "RequirementViewSet",
    "ArtifactViewSet",
    "ArchitectureElementViewSet",
    "TestCaseViewSet",
    "TraceLinkViewSet",
    "BaselineViewSet",
    "WorkflowDefinitionViewSet",
]
