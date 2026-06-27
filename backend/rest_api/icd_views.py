"""
COMP-RA-001 — IcdViewSet (REQ-L2-ICD-001).

Minimal REST endpoints for Interface Control Document (ICD) CRUD.

Endpoints:
  GET    /api/v1/icds/               — list ICDs (filter by workspace_id)
  POST   /api/v1/icds/               — create ICD with initial version
  GET    /api/v1/icds/<pk>/          — retrieve ICD details
  PATCH  /api/v1/icds/<pk>/          — update ICD (creates new version)
  DELETE /api/v1/icds/<pk>/          — delete ICD
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from icd.models import Icd, IcdDirection
from icd.services import (
    create_icd,
    update_icd,
    get_icd_history,
    IcdCreateDTO,
    IcdUpdateDTO,
)
from persistence.models import Tenant, User
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import StandardPagination, build_error_response, detect_lang


class IcdViewSet(ViewSet):
    """REST ViewSet for ICD CRUD operations."""

    pagination_class = StandardPagination

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

    # -- list --------------------------------------------------------------

    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/icds/ — list ICDs, filtered by workspace_id."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id = request.query_params.get("workspace_id")
            if not workspace_id:
                return Response(
                    build_error_response("VALIDATION_ERROR", lang, message="workspace_id is required"),
                    status=status.HTTP_400_BAD_REQUEST,
                )
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
            icd = Icd.objects.get(id=UUID(pk), tenant_id=ctx.tenant_id)
            # Get version info
            versions = get_icd_history(icd_id=UUID(pk))
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
            result = update_icd(icd_id=UUID(pk), payload=dto)
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
            icd = Icd.objects.get(id=UUID(pk), tenant_id=ctx.tenant_id)

            from django.db import connection

            with connection.cursor() as cursor:
                # Temporarily disable immutability trigger
                cursor.execute(
                    "ALTER TABLE icd_version DISABLE TRIGGER trg_icd_version_immutable"
                )
                try:
                    # Nullify FK to avoid constraint issues
                    icd.current_version = None
                    icd.save(update_fields=["current_version"])
                    # Delete versions
                    cursor.execute(
                        "DELETE FROM icd_version WHERE icd_id = %s",
                        [str(icd.id)],
                    )
                finally:
                    # Re-enable trigger
                    cursor.execute(
                        "ALTER TABLE icd_version ENABLE TRIGGER trg_icd_version_immutable"
                    )

            # Now delete the ICD itself (no child FK references remain)
            icd.delete()
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
