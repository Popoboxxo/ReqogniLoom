"""
COMP-RA-001 — Canvas & Mermaid sub-resource views (REQ-L1-056, REQ-L1-057).

Implements the REST endpoints specified in IF-L1-058..061:

  GET    /api/v1/diagrams/{id}/canvas-strokes/   — list strokes
  POST   /api/v1/diagrams/{id}/canvas-strokes/   — append strokes (auto-save)
  PUT    /api/v1/diagrams/{id}/canvas-strokes/   — replace strokes
  GET    /api/v1/diagrams/{id}/mermaid-source/   — get Mermaid source
  PUT    /api/v1/diagrams/{id}/mermaid-source/   — update Mermaid source
  GET    /api/v1/diagrams/{id}/mermaid-preview/  — rendered preview data

All views delegate to diagram.services (canvas_auto_save, get_canvas_diagram,
update_mermaid_source, get_mermaid_preview).  No direct ORM access.

Architecture:
  docs/se/L1/Gesamtsystem/L2/DiagramServiceSystem/
  L2_DiagramServiceSystem_Architecture.md
  docs/se/interface-registry.md §2.4 (IF-L1-058..061)
"""
from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from diagram.models import Diagram
from diagram.services import (
    canvas_auto_save,
    get_canvas_diagram,
    get_mermaid_preview,
    update_mermaid_source,
)
from diagram.validator import DiagramValidationError
from persistence.models import Tenant, User
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import build_error_response, detect_lang
from rest_api.serializers_diagram import (
    CanvasStrokeDataSerializer,
    CanvasStrokeResponseSerializer,
    MermaidPreviewResponseSerializer,
    MermaidSourceResponseSerializer,
    MermaidSourceSerializer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_tenant(request: Request) -> Tenant:
    """Resolve the Tenant ORM object from the request auth context."""
    ctx = get_auth_context(request)
    return Tenant.objects.get(id=ctx.tenant_id)


def _resolve_user(request: Request) -> User | None:
    """Resolve the User ORM object from the request auth context."""
    ctx = get_auth_context(request)
    return User.objects.filter(id=ctx.user_id).first()


def _verify_diagram_ownership(pk: str, tenant_id: str) -> Diagram:
    """Verify that the diagram exists and belongs to the tenant.

    Raises:
        Diagram.DoesNotExist: If not found or tenant mismatch.
    """
    return Diagram.objects.get(id=UUID(pk), tenant_id=tenant_id)


# ---------------------------------------------------------------------------
# Canvas Strokes — IF-L1-058 / IF-L1-060
# REQ-L1-056, REQ-L2-DS-006
# ---------------------------------------------------------------------------


class CanvasStrokeView(APIView):
    """REST view for canvas stroke operations on a specific diagram.

    Endpoints:
      GET  /api/v1/diagrams/{id}/canvas-strokes/ — retrieve stroke data + SVG
      POST /api/v1/diagrams/{id}/canvas-strokes/ — create/append (auto-save)
      PUT  /api/v1/diagrams/{id}/canvas-strokes/ — replace all strokes
    """

    # -- GET: retrieve canvas strokes ----------------------------------------

    @extend_schema(
        operation_id="diagrams_canvas_strokes_list",
        description="Retrieve all canvas strokes for a diagram (IF-L1-060).",
        responses={
            200: OpenApiResponse(
                response=CanvasStrokeResponseSerializer,
                description="Canvas stroke data with SVG export.",
            ),
            404: OpenApiResponse(description="Diagram not found."),
        },
        tags=["diagrams"],
    )
    def get(self, request: Request, pk: str) -> Response:
        """GET /api/v1/diagrams/{id}/canvas-strokes/"""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            _verify_diagram_ownership(pk, ctx.tenant_id)

            export_result = get_canvas_diagram(diagram_id=UUID(pk))
            stroke_data = export_result.stroke_data
            strokes = stroke_data.get("strokes", [])

            response_data = {
                "diagram_id": str(export_result.diagram_id),
                "strokes": strokes,
                "width": stroke_data.get("width", 800),
                "height": stroke_data.get("height", 600),
                "svg": export_result.svg,
                "version_number": (
                    export_result.version.version_number
                    if export_result.version
                    else None
                ),
            }

            serializer = CanvasStrokeResponseSerializer(response_data)
            return Response(serializer.data)

        except Diagram.DoesNotExist:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as exc:
            logger.exception("GET canvas-strokes failed for diagram %s", pk)
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang, message=str(exc)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # -- POST: append strokes (auto-save) ------------------------------------

    @extend_schema(
        operation_id="diagrams_canvas_strokes_append",
        description="Append strokes to a canvas diagram (IF-L1-058 auto-save).",
        request=CanvasStrokeDataSerializer,
        responses={
            200: OpenApiResponse(
                response=CanvasStrokeResponseSerializer,
                description="Updated canvas data.",
            ),
            400: OpenApiResponse(description="Validation error."),
            404: OpenApiResponse(description="Diagram not found."),
        },
        tags=["diagrams"],
    )
    def post(self, request: Request, pk: str) -> Response:
        """POST /api/v1/diagrams/{id}/canvas-strokes/ — auto-save."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            _verify_diagram_ownership(pk, ctx.tenant_id)

            serializer = CanvasStrokeDataSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            tenant = _resolve_tenant(request)
            user = _resolve_user(request)

            diagram = canvas_auto_save(
                stroke_data=serializer.validated_data,
                tenant=tenant,
                diagram_id=UUID(pk),
                user=user,
            )

            # Return updated canvas data
            export_result = get_canvas_diagram(diagram_id=diagram.id)
            stroke_data = export_result.stroke_data
            response_data = {
                "diagram_id": str(export_result.diagram_id),
                "strokes": stroke_data.get("strokes", []),
                "width": stroke_data.get("width", 800),
                "height": stroke_data.get("height", 600),
                "svg": export_result.svg,
                "version_number": (
                    export_result.version.version_number
                    if export_result.version
                    else None
                ),
            }

            resp_serializer = CanvasStrokeResponseSerializer(response_data)
            return Response(resp_serializer.data)

        except DRFValidationError as exc:
            # Serializer field validation failure (raise_exception=True) — return 400
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc.detail)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DiagramValidationError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Diagram.DoesNotExist:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as exc:
            logger.exception("POST canvas-strokes failed for diagram %s", pk)
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang, message=str(exc)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # -- PUT: replace all strokes --------------------------------------------

    @extend_schema(
        operation_id="diagrams_canvas_strokes_replace",
        description="Replace all strokes in a canvas diagram (full overwrite).",
        request=CanvasStrokeDataSerializer,
        responses={
            200: OpenApiResponse(
                response=CanvasStrokeResponseSerializer,
                description="Replaced canvas data.",
            ),
            400: OpenApiResponse(description="Validation error."),
            404: OpenApiResponse(description="Diagram not found."),
        },
        tags=["diagrams"],
    )
    def put(self, request: Request, pk: str) -> Response:
        """PUT /api/v1/diagrams/{id}/canvas-strokes/ — replace all."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            _verify_diagram_ownership(pk, ctx.tenant_id)

            serializer = CanvasStrokeDataSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            tenant = _resolve_tenant(request)
            user = _resolve_user(request)

            diagram = canvas_auto_save(
                stroke_data=serializer.validated_data,
                tenant=tenant,
                diagram_id=UUID(pk),
                user=user,
            )

            export_result = get_canvas_diagram(diagram_id=diagram.id)
            stroke_data = export_result.stroke_data
            response_data = {
                "diagram_id": str(export_result.diagram_id),
                "strokes": stroke_data.get("strokes", []),
                "width": stroke_data.get("width", 800),
                "height": stroke_data.get("height", 600),
                "svg": export_result.svg,
                "version_number": (
                    export_result.version.version_number
                    if export_result.version
                    else None
                ),
            }

            resp_serializer = CanvasStrokeResponseSerializer(response_data)
            return Response(resp_serializer.data)

        except DRFValidationError as exc:
            # Serializer field validation failure (raise_exception=True) — return 400
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc.detail)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DiagramValidationError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Diagram.DoesNotExist:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as exc:
            logger.exception("PUT canvas-strokes failed for diagram %s", pk)
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang, message=str(exc)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# ---------------------------------------------------------------------------
# Mermaid Source — IF-L1-059 / IF-L1-061
# REQ-L1-057, REQ-L2-DS-007
# ---------------------------------------------------------------------------


class MermaidSourceView(APIView):
    """REST view for Mermaid source code operations.

    Endpoints:
      GET /api/v1/diagrams/{id}/mermaid-source/ — get source code
      PUT /api/v1/diagrams/{id}/mermaid-source/ — update source code
    """

    # -- GET: retrieve Mermaid source ----------------------------------------

    @extend_schema(
        operation_id="diagrams_mermaid_source_retrieve",
        description="Retrieve Mermaid source code for a diagram.",
        responses={
            200: OpenApiResponse(
                response=MermaidSourceResponseSerializer,
                description="Mermaid source code.",
            ),
            404: OpenApiResponse(description="Diagram not found."),
        },
        tags=["diagrams"],
    )
    def get(self, request: Request, pk: str) -> Response:
        """GET /api/v1/diagrams/{id}/mermaid-source/"""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            _verify_diagram_ownership(pk, ctx.tenant_id)

            preview_data = get_mermaid_preview(diagram_id=UUID(pk))

            response_data = {
                "diagram_id": str(preview_data.diagram_id),
                "source": preview_data.source,
                "diagram_type": preview_data.diagram_type,
                "is_valid": not preview_data.fallback_mode,
                "error_message": preview_data.error_message,
            }

            serializer = MermaidSourceResponseSerializer(response_data)
            return Response(serializer.data)

        except Diagram.DoesNotExist:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as exc:
            logger.exception("GET mermaid-source failed for diagram %s", pk)
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang, message=str(exc)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # -- PUT: update Mermaid source ------------------------------------------

    @extend_schema(
        operation_id="diagrams_mermaid_source_update",
        description="Update Mermaid source code (IF-L1-059).",
        request=MermaidSourceSerializer,
        responses={
            200: OpenApiResponse(
                response=MermaidSourceResponseSerializer,
                description="Updated Mermaid source.",
            ),
            400: OpenApiResponse(description="Validation error."),
            404: OpenApiResponse(description="Diagram not found."),
        },
        tags=["diagrams"],
    )
    def put(self, request: Request, pk: str) -> Response:
        """PUT /api/v1/diagrams/{id}/mermaid-source/ — update source."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            _verify_diagram_ownership(pk, ctx.tenant_id)

            serializer = MermaidSourceSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            tenant = _resolve_tenant(request)
            user = _resolve_user(request)

            diagram = update_mermaid_source(
                diagram_id=UUID(pk),
                source=serializer.validated_data["source"],
                tenant=tenant,
                user=user,
            )

            # Return updated source data
            preview_data = get_mermaid_preview(diagram_id=diagram.id)
            response_data = {
                "diagram_id": str(preview_data.diagram_id),
                "source": preview_data.source,
                "diagram_type": preview_data.diagram_type,
                "is_valid": not preview_data.fallback_mode,
                "error_message": preview_data.error_message,
            }

            resp_serializer = MermaidSourceResponseSerializer(response_data)
            return Response(resp_serializer.data)

        except DRFValidationError as exc:
            # Serializer field validation failure (raise_exception=True) — return 400
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc.detail)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DiagramValidationError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Diagram.DoesNotExist:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as exc:
            logger.exception("PUT mermaid-source failed for diagram %s", pk)
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang, message=str(exc)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# ---------------------------------------------------------------------------
# Mermaid Preview — IF-L1-061
# REQ-L1-057, REQ-L2-DS-007
# ---------------------------------------------------------------------------


class MermaidPreviewView(APIView):
    """REST view for Mermaid preview data.

    Endpoint:
      GET /api/v1/diagrams/{id}/mermaid-preview/ — rendered preview (SVG + hints)
    """

    @extend_schema(
        operation_id="diagrams_mermaid_preview_retrieve",
        description="Retrieve Mermaid live preview data (IF-L1-061).",
        responses={
            200: OpenApiResponse(
                response=MermaidPreviewResponseSerializer,
                description="Preview data with source, render hints, fallback info.",
            ),
            404: OpenApiResponse(description="Diagram not found."),
        },
        tags=["diagrams"],
    )
    def get(self, request: Request, pk: str) -> Response:
        """GET /api/v1/diagrams/{id}/mermaid-preview/"""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            _verify_diagram_ownership(pk, ctx.tenant_id)

            preview_data = get_mermaid_preview(diagram_id=UUID(pk))

            response_data = {
                "diagram_id": str(preview_data.diagram_id),
                "source": preview_data.source,
                "diagram_type": preview_data.diagram_type,
                "render_hints": (
                    {
                        "supported_formats": preview_data.render_hints.supported_formats,
                        "renderer": preview_data.render_hints.renderer,
                        "notes": preview_data.render_hints.notes,
                    }
                    if preview_data.render_hints
                    else None
                ),
                "fallback_mode": preview_data.fallback_mode,
                "error_message": preview_data.error_message,
            }

            serializer = MermaidPreviewResponseSerializer(response_data)
            return Response(serializer.data)

        except Diagram.DoesNotExist:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as exc:
            logger.exception("GET mermaid-preview failed for diagram %s", pk)
            return Response(
                build_error_response("INTERNAL_SERVER_ERROR", lang, message=str(exc)),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
