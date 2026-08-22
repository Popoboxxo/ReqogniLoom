"""
COMP-RA-001 — DiagramViewSet (REQ-L2-DS-001).

Minimal REST endpoints for Diagram CRUD.

Endpoints:
  GET    /api/v1/diagrams/           — list diagrams (filter by workspace_id)
  POST   /api/v1/diagrams/           — create diagram with initial version
  GET    /api/v1/diagrams/<pk>/      — retrieve diagram details
  PATCH  /api/v1/diagrams/<pk>/      — update diagram (creates new version)
  DELETE /api/v1/diagrams/<pk>/      — delete diagram
  GET    /api/v1/diagrams/<pk>/versions/ — list DiagramVersions chronologically
  GET    /api/v1/diagrams/<pk>/diff/     — field-level diff between two versions
                                            (?from_version=&to_version=)
  GET/POST /api/v1/diagrams/<pk>/transitions/      — workflow transitions (REQ-173)
  GET    /api/v1/diagrams/<pk>/workflow-history/   — workflow audit trail (REQ-173)

REQ-142: versions/diff delegate to ArtifactDiffService (COMP-AS-019), reusing
the same field-level diff computation as the requirement endpoints.

REQ-173: WorkflowTransitionsMixin wires Diagram into the shared lifecycle
machinery. workspace_id is set on creation and stored directly on Diagram
(mirrors Icd); workflow endpoints require a non-null workspace_id.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from application.artifact_diff_service import ArtifactDiffService
from application.base import NotFoundError
from diagram.models import Diagram, DiagramType, PayloadFormat
from diagram.services import (
    create_diagram,
    delete_diagram,
    get_diagram,
    get_diagram_header,
    list_versions,
    update_diagram,
    DiagramResult,
    DiagramValidationError,
)
from persistence.models import Tenant, User
from rest_api.auth_enforcer import get_auth_context
from rest_api.mixins.workflow_transitions import WorkflowTransitionsMixin
from rest_api.query_params import parse_workspace_id
from rest_api.serializers import StandardPagination, build_error_response, detect_lang
from traceability.exceptions import TraceLinkError

logger = logging.getLogger(__name__)


class DiagramViewSet(WorkflowTransitionsMixin, ViewSet):
    """REST ViewSet for Diagram CRUD operations.

    REQ-173: transitions/ and workflow-history/ via WorkflowTransitionsMixin,
    same lifecycle machinery as Icd/Requirement/... Diagram.workspace_id is
    nullable (migration 0005, Expand phase) — existing rows predate workspace
    scoping and are backfilled separately, so workflow access is only
    available once a diagram has a workspace assigned (see
    _resolve_workflow_target below).
    """

    pagination_class = StandardPagination
    workflow_item_type = "Diagram"

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

    def _diagram_to_dict(self, diagram: Diagram) -> dict[str, Any]:
        return {
            "id": str(diagram.id),
            "name": diagram.name,
            "diagram_type": diagram.diagram_type,
            "description": diagram.description,
            "workspace_id": str(diagram.workspace_id) if diagram.workspace_id else None,
            "current_version": str(diagram.current_version_id) if diagram.current_version_id else None,
            "created_at": diagram.created_at.isoformat() if diagram.created_at else None,
            "version_count": diagram.versions.count() if diagram.id else 0,
        }

    # -- workflow (REQ-173) --------------------------------------------------

    def _resolve_workflow_target(self, pk: str, ctx: Any) -> tuple[UUID, UUID]:
        """Resolve the Diagram identified by *pk* to (item_id, workspace_id).

        Diagram stores workspace_id directly (see _diagram_to_dict), mirroring
        the Icd pattern. workspace_id is nullable for pre-existing rows
        (migration 0005, Expand phase) — those are backfilled separately, so
        workflow transitions are only available once a diagram has a
        workspace assigned.
        """
        try:
            diagram = get_diagram_header(UUID(pk), ctx.tenant_id)
        except Diagram.DoesNotExist as exc:
            raise NotFoundError(str(exc)) from exc
        if diagram.workspace_id is None:
            raise NotFoundError(
                f"Diagram {diagram.id} has no workspace assigned; workflow unavailable"
            )
        return diagram.id, diagram.workspace_id

    # -- list --------------------------------------------------------------

    def list(self, request: Request, **kwargs: Any) -> Response:
        """GET /api/v1/diagrams/ — list diagrams, filtered by workspace_id."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            workspace_id, error = parse_workspace_id(
                request.query_params.get("workspace_id"),
                lang,
            )
            if error is not None:
                return error
            # Tenant-scoped query filtered by workspace_id
            diagrams = Diagram.objects.filter(
                workspace_id=workspace_id,
                tenant_id=ctx.tenant_id,
            ).order_by("-created_at")
            serialized = [self._diagram_to_dict(d) for d in diagrams]
            return self._paginate(request, serialized)
        except Exception:
            logger.exception("GET /diagrams/ list failed")
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # -- create ------------------------------------------------------------

    def create(self, request: Request, **kwargs: Any) -> Response:
        """POST /api/v1/diagrams/ — create a new diagram with initial version."""
        lang = detect_lang(request)
        try:
            name = request.data.get("name")
            diagram_type = request.data.get("diagram_type", DiagramType.BLOCK)
            payload_format = request.data.get("payload_format", PayloadFormat.JSON)
            content = request.data.get("content", "{}")
            description = request.data.get("description", "")
            workspace_id_raw = request.data.get("workspace_id")

            if not name or not str(name).strip():
                return Response(
                    build_error_response("VALIDATION_ERROR", lang, message="name is required"),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            workspace_id: UUID | None = None
            if workspace_id_raw:
                try:
                    workspace_id = UUID(str(workspace_id_raw))
                except (ValueError, TypeError):
                    return Response(
                        build_error_response(
                            "VALIDATION_ERROR", lang, message="workspace_id must be a valid UUID"
                        ),
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            tenant = self._resolve_tenant(request)
            user = self._resolve_user(request)

            diagram = create_diagram(
                name=str(name).strip(),
                diagram_type=str(diagram_type),
                payload_format=str(payload_format),
                content=str(content),
                tenant=tenant,
                description=str(description),
                created_by=user,
                workspace_id=workspace_id,
            )
            return Response(
                self._diagram_to_dict(diagram),
                status=status.HTTP_201_CREATED,
            )
        except DiagramValidationError as exc:
            # REQ-L3-DV-001/CR-02: payload failed type-specific validation
            # (e.g. type=block without 'nodes') — fail cleanly with 400
            # instead of leaking as an unhandled 500.
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except TraceLinkError as exc:
            # M4 (Codeberg #353 final review): a node_graph payload's
            # artifact_ref reconciliation can raise TraceLinkError (e.g. a
            # workspace-less legacy Diagram) — this is a client-input
            # problem, not a server fault, so it maps to 400 the same as
            # DiagramValidationError above rather than falling through to
            # the generic 500 handler below.
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            logger.exception("POST /diagrams/ create failed")
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # -- retrieve ----------------------------------------------------------

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/diagrams/<pk>/ — get diagram details with version info."""
        lang = detect_lang(request)
        try:
            result: DiagramResult = get_diagram(diagram_id=UUID(pk))
            diagram = result.diagram
            version = result.version
            return Response({
                "id": str(diagram.id),
                "name": diagram.name,
                "diagram_type": diagram.diagram_type,
                "description": diagram.description,
                "payload_format": version.payload_format if version else None,
                "content": version.payload if version else None,
                "version_number": version.version_number if version else None,
                "created_at": diagram.created_at.isoformat() if diagram.created_at else None,
            })
        except Diagram.DoesNotExist:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception:
            logger.exception("GET /diagrams/%s/ retrieve failed", pk)
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # -- partial_update ----------------------------------------------------

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """PATCH /api/v1/diagrams/<pk>/ — update diagram (creates new version)."""
        lang = detect_lang(request)
        try:
            payload_format = request.data.get("payload_format")
            content = request.data.get("content")

            if not payload_format or not content:
                return Response(
                    build_error_response("VALIDATION_ERROR", lang, message="payload_format and content are required"),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = self._resolve_user(request)
            new_version = update_diagram(
                diagram_id=UUID(pk),
                payload_format=str(payload_format),
                content=str(content),
                modified_by=user,
            )
            return Response({
                "version_number": new_version.version_number,
                "payload_format": new_version.payload_format,
                "content": new_version.payload,
            })
        except Diagram.DoesNotExist:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        except DiagramValidationError as exc:
            # Same validation-before-persistence contract as create() (CR-02).
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except TraceLinkError as exc:
            # M4 (Codeberg #353 final review): see create()'s identical
            # handler above — a workspace-less legacy Diagram's node_graph
            # artifact_ref reconciliation is a client-input problem (400),
            # not a server fault (500).
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            logger.exception("PATCH /diagrams/%s/ update failed", pk)
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # -- destroy -----------------------------------------------------------

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """DELETE /api/v1/diagrams/<pk>/ — delete a diagram and all versions."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            delete_diagram(UUID(pk), ctx.tenant_id, ctx=ctx)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Diagram.DoesNotExist:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception:
            logger.exception("DELETE /diagrams/%s/ destroy failed", pk)
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # -- versions (REQ-142) -------------------------------------------------

    @action(detail=True, methods=["get"], url_path="versions")
    def versions(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/diagrams/<pk>/versions/ — list DiagramVersions chronologically.

        REQ-142: delegates to ArtifactDiffService (COMP-AS-019).
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            result = ArtifactDiffService().list_versions_for_diagram(UUID(pk), ctx)
            return Response(result)
        except NotFoundError as exc:
            return Response(
                build_error_response("NOT_FOUND", lang, message=str(exc)),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception:
            logger.exception("GET /diagrams/%s/versions/ failed", pk)
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # -- diff (REQ-142) ------------------------------------------------------

    @action(detail=True, methods=["get"], url_path="diff")
    def diff(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/diagrams/<pk>/diff/?from_version=0&to_version=2

        REQ-142: Structured field-level diff between two DiagramVersions.
        Delegates to ArtifactDiffService (COMP-AS-019); reuses the same
        diff computation as the requirement diff endpoint.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            diagram_id = UUID(pk)

            try:
                result: DiagramResult = get_diagram(diagram_id=diagram_id)
            except Diagram.DoesNotExist:
                return Response(
                    build_error_response("NOT_FOUND", lang),
                    status=status.HTTP_404_NOT_FOUND,
                )
            default_to_version = (
                result.version.version_number if result.version else 0
            )

            from_version = int(request.query_params.get("from_version", "0"))
            to_version = int(
                request.query_params.get("to_version", str(default_to_version))
            )

            result = ArtifactDiffService().diff_for_diagram(
                diagram_id=diagram_id,
                from_version=from_version,
                to_version=to_version,
                ctx=ctx,
            )
            return Response(result)
        except NotFoundError as exc:
            return Response(
                build_error_response("NOT_FOUND", lang, message=str(exc)),
                status=status.HTTP_404_NOT_FOUND,
            )
        except ValueError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            logger.exception("GET /diagrams/%s/diff/ failed", pk)
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
