"""
COMP-RA-001 — IcdViewSet (REQ-L2-ICD-001, REQ-L2-ICD-002).

Minimal REST endpoints for Interface Control Document (ICD) CRUD.

Endpoints:
  GET    /api/v1/icds/                                  — list ICDs (filter by workspace_id)
  POST   /api/v1/icds/                                  — create ICD with initial version
  GET    /api/v1/icds/<pk>/                             — retrieve ICD details
  PATCH  /api/v1/icds/<pk>/                             — update ICD (creates new version)
  DELETE /api/v1/icds/<pk>/                             — delete ICD

Structured interface parameters (REQ-L2-ICD-002, COMP-ICD-001):
  GET    /api/v1/icds/<pk>/parameters/?version=<n>      — list parameters (default: current version)
  POST   /api/v1/icds/<pk>/parameters/                  — create a parameter (body: version=<n>, default: current)
  PATCH  /api/v1/icds/<pk>/parameters/<parameter_id>/   — update a parameter
  DELETE /api/v1/icds/<pk>/parameters/<parameter_id>/   — delete a parameter
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from application.artifact_diff_service import creation_baseline_entry
from application.base import NotFoundError
from icd.models import Icd, IcdDirection, IcdParameter, IcdVersion
from icd.services import (
    create_icd,
    create_icd_parameter,
    delete_icd,
    delete_icd_parameter,
    get_icd,
    update_icd,
    update_icd_parameter,
    get_icd_history,
    find_similar_icds,
    list_icd_parameters,
    IcdCreateDTO,
    IcdParameterCreateDTO,
    IcdParameterNotFoundError,
    IcdParameterUpdateDTO,
    IcdPgVectorUnavailableError,
    IcdUpdateDTO,
)
from persistence.models import Tenant, User
from rest_api.auth_enforcer import get_auth_context
from rest_api.mixins.workflow_transitions import WorkflowTransitionsMixin
from rest_api.query_params import parse_workspace_id
from rest_api.serializers import (
    IcdParameterSerializer,
    StandardPagination,
    build_error_response,
    detect_lang,
)


class IcdViewSet(WorkflowTransitionsMixin, ViewSet):
    """REST ViewSet for ICD CRUD operations.

    REQ-173: transitions/ and workflow-history/ via WorkflowTransitionsMixin
    so ICDs share the same lifecycle machinery as every other artifact type.
    """

    pagination_class = StandardPagination
    workflow_item_type = "Icd"

    # -- helpers -----------------------------------------------------------

    @property
    def paginator(self) -> StandardPagination:
        if not hasattr(self, "_paginator"):
            self._paginator = self.pagination_class()
        return self._paginator

    def _paginate(self, request: Request, data: list) -> Response:
        page = self.paginator.paginate_queryset(data, request, view=self)
        if page is not None:
            return self.paginator.get_paginated_response(page)
        return Response(data)

    def _resolve_tenant(self, request: Request) -> Tenant:
        ctx = get_auth_context(request)
        return Tenant.objects.get(id=ctx.tenant_id)

    def _resolve_user(self, request: Request) -> User | None:
        ctx = get_auth_context(request)
        return User.objects.filter(id=ctx.user_id).first()

    def _icd_to_dict(self, icd: Icd) -> dict[str, Any]:
        return {
            "id": str(icd.id),
            "name": icd.name,
            "workspace_id": str(icd.workspace_id),
            "source_element_id": str(icd.source_element_id),
            "target_element_id": str(icd.target_element_id),
            "current_version": str(icd.current_version_id) if icd.current_version_id else None,
            "created_at": icd.created_at.isoformat() if icd.created_at else None,
        }

    def _parameter_to_dict(self, param: IcdParameter) -> dict[str, Any]:
        """Convert IcdParameter ORM object to serializer-compatible dict."""
        return {
            "id": str(param.id),
            "icd_version_id": str(param.icd_version_id),
            "name": param.name,
            "description": param.description,
            "unit": param.unit,
            "data_type": param.data_type,
            "direction": param.direction,
            "min_value": param.min_value,
            "max_value": param.max_value,
            "nominal_value": param.nominal_value,
            "tolerance": param.tolerance,
            "ordering": param.ordering,
            "created_at": param.created_at.isoformat() if param.created_at else None,
            "updated_at": param.modified_at.isoformat() if param.modified_at else None,
        }

    def _resolve_icd_version(self, icd: Icd, version_param: str | None) -> IcdVersion:
        """Resolve a version_number query/body param to its IcdVersion.

        Defaults to the ICD's current version when *version_param* is None.

        Raises:
            IcdVersion.DoesNotExist: No matching version found.
        """
        if version_param is None or version_param == "":
            if icd.current_version_id is None:
                raise IcdVersion.DoesNotExist(f"ICD {icd.id} has no current version")
            return icd.current_version
        target_number = int(version_param)
        version_list = get_icd_history(icd_id=icd.id, tenant_id=icd.tenant_id)
        match = next(
            (v for v in version_list if v.version_number == target_number), None
        )
        if match is None:
            raise IcdVersion.DoesNotExist(
                f"IcdVersion number {target_number} not found for ICD {icd.id}"
            )
        return match

    # -- workflow (REQ-173) --------------------------------------------------

    def _resolve_workflow_target(self, pk: str, ctx: Any) -> tuple[UUID, UUID]:
        """Resolve the Icd identified by *pk* to (item_id, workspace_id).

        Icd stores workspace_id directly (see _icd_to_dict), unlike
        ArchitectureElement which is scoped via its artifact.
        """
        try:
            icd = get_icd(UUID(pk), ctx.tenant_id)
        except Icd.DoesNotExist as exc:
            raise NotFoundError(str(exc)) from exc
        return icd.id, icd.workspace_id

    # -- list --------------------------------------------------------------

    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/icds/ — list ICDs, filtered by workspace_id."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id, error = parse_workspace_id(
                request.query_params.get("workspace_id"),
                lang,
            )
            if error is not None:
                return error
            icds = Icd.objects.filter(
                workspace_id=workspace_id,
                tenant_id=ctx.tenant_id,
            ).order_by("-created_at")
            serialized = [self._icd_to_dict(icd) for icd in icds]
            return self._paginate(request, serialized)
        except Exception as exc:
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang, message=str(exc)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # -- create ------------------------------------------------------------

    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/icds/ — create a new ICD with initial version."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            tenant = self._resolve_tenant(request)
            user = self._resolve_user(request)

            name = request.data.get("name")
            workspace_id = request.data.get("workspace_id")
            source_element_id = request.data.get("source_element_id")
            target_element_id = request.data.get("target_element_id")

            if not name or not workspace_id or not source_element_id or not target_element_id:
                return Response(
                    build_error_response(
                        "VALIDATION_ERROR", lang,
                        message="name, workspace_id, source_element_id, target_element_id are required",
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            dto = IcdCreateDTO(
                tenant_id=tenant.id,
                workspace_id=UUID(str(workspace_id)),
                name=str(name).strip(),
                source_element_id=UUID(str(source_element_id)),
                target_element_id=UUID(str(target_element_id)),
                direction=request.data.get("direction", IcdDirection.UNIDIRECTIONAL),
                interface_type=request.data.get("interface_type", ""),
                semantic_description=request.data.get("semantic_description", ""),
                preconditions=request.data.get("preconditions", []),
                postconditions=request.data.get("postconditions", []),
                invariants=request.data.get("invariants", []),
                created_by_id=str(user.id) if user else None,
            )
            result = create_icd(dto)
            return Response(
                {
                    "id": str(result.icd.id),
                    "name": result.icd.name,
                    "workspace_id": str(result.icd.workspace_id),
                    "source_element_id": str(result.icd.source_element_id),
                    "target_element_id": str(result.icd.target_element_id),
                    "version": result.current_version.version_number if result.current_version else 1,
                    "created_at": result.icd.created_at.isoformat() if result.icd.created_at else None,
                },
                status=status.HTTP_201_CREATED,
            )
        except ValueError as exc:
            # #104: create_icd() raises ValueError on ContractValidator syntax
            # failures (missing fields, wrong types, oversized free-text —
            # SEMANTIC_DESCRIPTION_MAX_LENGTH). This is a client input error,
            # not a server fault, so map it to 400 instead of falling through
            # to the generic 500 handler below.
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang, message=str(exc)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # -- retrieve ----------------------------------------------------------

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/icds/<pk>/ — retrieve ICD details with current version info."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            icd = get_icd(UUID(pk), ctx.tenant_id)
            # Get version info
            versions = get_icd_history(icd_id=UUID(pk), tenant_id=ctx.tenant_id)
            current_version = versions[-1] if versions else None
            return Response({
                "id": str(icd.id),
                "name": icd.name,
                "workspace_id": str(icd.workspace_id),
                "source_element_id": str(icd.source_element_id),
                "target_element_id": str(icd.target_element_id),
                "version": current_version.version_number if current_version else 1,
                "direction": current_version.direction if current_version else None,
                "interface_type": current_version.interface_type if current_version else None,
                "semantic_description": current_version.semantic_description if current_version else None,
                "preconditions": current_version.preconditions if current_version else [],
                "postconditions": current_version.postconditions if current_version else [],
                "invariants": current_version.invariants if current_version else [],
                "created_at": icd.created_at.isoformat() if icd.created_at else None,
            })
        except Icd.DoesNotExist:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as exc:
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang, message=str(exc)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # -- partial_update ----------------------------------------------------

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """PATCH /api/v1/icds/<pk>/ — update ICD (creates new version)."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            user = self._resolve_user(request)

            dto = IcdUpdateDTO(
                direction=request.data.get("direction"),
                interface_type=request.data.get("interface_type"),
                semantic_description=request.data.get("semantic_description"),
                preconditions=request.data.get("preconditions"),
                postconditions=request.data.get("postconditions"),
                invariants=request.data.get("invariants"),
                modified_by_id=str(user.id) if user else None,
            )
            result = update_icd(icd_id=UUID(pk), payload=dto, tenant_id=ctx.tenant_id)
            return Response({
                "id": str(result.icd.id),
                "name": result.icd.name,
                "version": result.current_version.version_number if result.current_version else 1,
                "direction": result.current_version.direction if result.current_version else None,
            })
        except Icd.DoesNotExist:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        except ValueError as exc:
            # #104: see create() — syntax/size validation errors are client
            # errors (400), not server faults.
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang, message=str(exc)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # -- destroy -----------------------------------------------------------

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/icds/<pk>/ — delete an ICD and all versions.

        Note: IcdVersion records are immutable via DB trigger (ADR-ICD-01).
        We temporarily disable the trigger to allow deletion.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            delete_icd(UUID(pk), ctx.tenant_id)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Icd.DoesNotExist:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as exc:
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang, message=str(exc)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # -- versions ----------------------------------------------------------

    @action(detail=True, methods=["get"], url_path="versions")
    def versions(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/icds/<pk>/versions/ — list available versions."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            icd = get_icd(UUID(pk), ctx.tenant_id)
            version_list = get_icd_history(icd_id=icd.id, tenant_id=ctx.tenant_id)
            result = [creation_baseline_entry()]
            for v in version_list:
                result.append({
                    "version": v.version_number,
                    "label": f"v{v.version_number}",
                    "modified_at": v.created_at.isoformat() if v.created_at else None,
                    # ICDs keep real immutable version rows (IcdVersion), so
                    # every listed version has retrievable content (#213).
                    "content_available": True,
                })
            return Response(result)
        except Icd.DoesNotExist:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as exc:
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang, message=str(exc)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # -- diff --------------------------------------------------------------

    @action(detail=True, methods=["get"], url_path="diff")
    def diff(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/icds/<pk>/diff/?from_version=1&to_version=2

        REQ-L1-090 / REQ-L1-091: Structured field-level diff for ICDs.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            icd = get_icd(UUID(pk), ctx.tenant_id)

            from_version = int(request.query_params.get("from_version", "0"))
            current_ver = icd.current_version.version_number if icd.current_version else 1
            to_version = int(request.query_params.get("to_version", str(current_ver)))

            version_list = get_icd_history(icd_id=icd.id, tenant_id=ctx.tenant_id)
            from_v = next((v for v in version_list if v.version_number == from_version), None)
            to_v = next((v for v in version_list if v.version_number == to_version), None)

            if to_v is None:
                return Response(
                    build_error_response("NOT_FOUND", lang, message=f"Version {to_version} not found"),
                    status=status.HTTP_404_NOT_FOUND,
                )

            fields = []
            # Compare Design-by-Contract fields
            dbc_fields = ["direction", "interface_type", "semantic_description", "preconditions", "postconditions", "invariants"]
            for field_name in dbc_fields:
                from_val = getattr(from_v, field_name, None) if from_v else None
                to_val = getattr(to_v, field_name, None)
                
                if from_v is None:
                    # Version 0 = creation baseline
                    fields.append({
                        "name": field_name,
                        "status": "added",
                        "to": to_val,
                    })
                elif from_val != to_val:
                    fields.append({
                        "name": field_name,
                        "status": "modified",
                        "from": from_val,
                        "to": to_val,
                    })
                else:
                    fields.append({
                        "name": field_name,
                        "status": "unchanged",
                        "from": from_val,
                        "to": to_val,
                    })

            result = {
                "from_version": from_version,
                "to_version": to_version,
                "entity_type": "Icd",
                "fields": fields,
            }
            return Response(result)
        except Icd.DoesNotExist:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as exc:
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang, message=str(exc)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # -- similar -----------------------------------------------------------

    @action(detail=True, methods=["get"], url_path="similar")
    def similar(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/icds/<pk>/similar/?limit=10 — semantic similarity search.

        REQ-L2-VS-004: Returns the top-N ICDs most similar to <pk> by cosine
        distance over the current IcdVersion's pgvector embedding. Returns 400
        when the ICD has no embedding, 503 when pgvector is unavailable.
        """
        lang = detect_lang(request)
        try:
            limit = int(request.query_params.get("limit", "10"))
        except (ValueError, TypeError):
            limit = 10

        try:
            ctx = get_auth_context(request)
            results = find_similar_icds(
                icd_id=UUID(pk),
                tenant_id=ctx.tenant_id,
                limit=limit,
            )
        except Icd.DoesNotExist:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except IcdPgVectorUnavailableError as exc:
            return Response(
                build_error_response("SERVICE_UNAVAILABLE", lang, message=str(exc)),
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as exc:
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang, message=str(exc)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            [
                {
                    "icd_id": str(hit.icd_id),
                    "version_id": str(hit.version_id),
                    "name": hit.name,
                    "interface_type": hit.interface_type,
                    "version_number": hit.version_number,
                    "similarity_score": hit.similarity_score,
                }
                for hit in results
            ]
        )

    # -- parameters (REQ-L2-ICD-002) ---------------------------------------

    @action(detail=True, methods=["get", "post"], url_path="parameters")
    def parameters(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET/POST /api/v1/icds/<pk>/parameters/?version=<n>

        GET  — list structured parameters for a version (default: current).
        POST — create a structured parameter on a version (default: current).
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            icd = get_icd(UUID(pk), ctx.tenant_id)
        except Icd.DoesNotExist:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as exc:
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang, message=str(exc)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if request.method == "GET":
            try:
                version = self._resolve_icd_version(
                    icd, request.query_params.get("version")
                )
                items = list_icd_parameters(
                    icd_version_id=version.id, tenant_id=ctx.tenant_id
                )
            except IcdVersion.DoesNotExist as exc:
                return Response(
                    build_error_response("NOT_FOUND", lang, message=str(exc)),
                    status=status.HTTP_404_NOT_FOUND,
                )
            except Exception as exc:
                return Response(
                    build_error_response("INTERNAL_SERVER_ERROR", lang, message=str(exc)),
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            serialized = [self._parameter_to_dict(item) for item in items]
            return self._paginate(request, serialized)

        # POST — create
        ser = IcdParameterSerializer(data=request.data)
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
            version = self._resolve_icd_version(icd, request.data.get("version"))
            payload = IcdParameterCreateDTO(
                icd_version_id=version.id,
                name=data["name"],
                unit=data.get("unit", ""),
                data_type=data.get("data_type", "other"),
                direction=data.get("direction", "input"),
                description=data.get("description", ""),
                min_value=data.get("min_value"),
                max_value=data.get("max_value"),
                nominal_value=data.get("nominal_value", ""),
                tolerance=data.get("tolerance", ""),
                ordering=data.get("ordering", 0),
            )
            item = create_icd_parameter(payload, tenant_id=ctx.tenant_id)
        except IcdVersion.DoesNotExist as exc:
            return Response(
                build_error_response("NOT_FOUND", lang, message=str(exc)),
                status=status.HTTP_404_NOT_FOUND,
            )
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang, message=str(exc)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return Response(
            IcdParameterSerializer(self._parameter_to_dict(item)).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=["patch", "delete"],
        url_path=r"parameters/(?P<parameter_id>[0-9a-fA-F-]{36})",
    )
    def parameter_detail(
        self, request: Request, pk: str, parameter_id: str, **kwargs: Any
    ) -> Response:
        """PATCH/DELETE /api/v1/icds/<pk>/parameters/<parameter_id>/

        PATCH  — update a structured parameter.
        DELETE — delete a structured parameter.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception as exc:
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang, message=str(exc)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if request.method == "DELETE":
            try:
                delete_icd_parameter(UUID(parameter_id), tenant_id=ctx.tenant_id)
            except IcdParameterNotFoundError as exc:
                return Response(
                    build_error_response("NOT_FOUND", lang, message=str(exc)),
                    status=status.HTTP_404_NOT_FOUND,
                )
            except Exception as exc:
                return Response(
                    build_error_response("INTERNAL_SERVER_ERROR", lang, message=str(exc)),
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            return Response(status=status.HTTP_204_NO_CONTENT)

        # PATCH — update
        ser = IcdParameterSerializer(data=request.data, partial=True)
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
            payload = IcdParameterUpdateDTO(
                name=data.get("name"),
                unit=data.get("unit"),
                data_type=data.get("data_type"),
                direction=data.get("direction"),
                description=data.get("description"),
                min_value=data.get("min_value"),
                max_value=data.get("max_value"),
                nominal_value=data.get("nominal_value"),
                tolerance=data.get("tolerance"),
                ordering=data.get("ordering"),
            )
            item = update_icd_parameter(
                UUID(parameter_id), payload, tenant_id=ctx.tenant_id
            )
        except IcdParameterNotFoundError as exc:
            return Response(
                build_error_response("NOT_FOUND", lang, message=str(exc)),
                status=status.HTTP_404_NOT_FOUND,
            )
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang, message=str(exc)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return Response(IcdParameterSerializer(self._parameter_to_dict(item)).data)
