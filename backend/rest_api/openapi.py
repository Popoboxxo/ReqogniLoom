"""
COMP-RA-005 OpenApiGenerator — drf-spectacular OpenAPI-3.0 schema + Swagger UI.

leaf_id : COMP-RA-005
req_id  : REQ-L2-RA-002 (OpenAPI spec + Swagger-UI)
          REQ-L3-RA005-001, REQ-L3-RA005-002, REQ-L3-RA005-003

Architecture:
  docs/se/L1/Gesamtsystem/L2/RestApiAdapterSystem/Components/
    COMP-RA-005_OpenApiGenerator/L3_COMP-RA-005_OpenApiGenerator_Architecture.md

Interfaces:
  IF-RA-EXT-OUT-002  -> /api/v1/schema/          (OpenAPI-3.0 JSON)
  IF-RA-EXT-OUT-003  -> /api/v1/schema/swagger-ui/ (Swagger UI HTML)
  IF-RA-INT-005      -> COMP-RA-001 (EndpointRegistry — implicit via DRF router)
  IF-RA-INT-006      -> COMP-RA-002 (SerializerSchemas — implicit via DRF introspection)

Design:
  - drf-spectacular handles OpenAPI generation from registered ViewSets.
  - Schema endpoint is accessible without authentication (REQ-L3-RA005-001 AC).
  - Swagger-UI is accessible without authentication (REQ-L3-RA005-002 AC).
  - Security scheme (Bearer Token) is defined in SPECTACULAR_SETTINGS.
  - This module wires custom drf-spectacular hooks for standardized error schemas.
"""
from __future__ import annotations

from drf_spectacular.extensions import OpenApiSerializerExtension
from drf_spectacular.plumbing import build_basic_type
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import serializers


# ---------------------------------------------------------------------------
# Standardized error response schema (REQ-L2-RA-009)
# ---------------------------------------------------------------------------


class ErrorDetailSerializer(serializers.Serializer):
    """Schema for field-level error detail."""

    field = serializers.CharField()
    errors = serializers.ListField(child=serializers.CharField())


class ErrorBodySerializer(serializers.Serializer):
    """Schema for the inner error object."""

    code = serializers.CharField(help_text="Machine-readable error code.")
    message = serializers.CharField(help_text="Human-readable localized message.")
    details = ErrorDetailSerializer(many=True, required=False)


class ErrorResponseSerializer(serializers.Serializer):
    """Standard error response shape (REQ-L2-RA-009).

    Format: {"error": {"code": "...", "message": "...", "details": [...]}}
    """

    error = ErrorBodySerializer()


# ---------------------------------------------------------------------------
# Common OpenAPI responses for use in extend_schema decorators
# ---------------------------------------------------------------------------

COMMON_ERROR_RESPONSES = {
    400: OpenApiResponse(
        response=ErrorResponseSerializer,
        description="Validation error.",
        examples=[
            OpenApiExample(
                "ValidationError",
                value={"error": {"code": "VALIDATION_ERROR", "message": "Validation failed.", "details": []}},
            )
        ],
    ),
    401: OpenApiResponse(
        response=ErrorResponseSerializer,
        description="Authentication required.",
    ),
    403: OpenApiResponse(
        response=ErrorResponseSerializer,
        description="RBAC permission denied.",
    ),
    404: OpenApiResponse(
        response=ErrorResponseSerializer,
        description="Resource not found.",
    ),
    500: OpenApiResponse(
        response=ErrorResponseSerializer,
        description="Internal server error.",
    ),
}


# ---------------------------------------------------------------------------
# drf-spectacular security scheme registration
# REQ-L3-RA005-001: securitySchemes defines Bearer token authentication.
# Registered via SPECTACULAR_SETTINGS in settings.py.
# ---------------------------------------------------------------------------
# The BearerToken security scheme is defined in settings.py under:
#   SPECTACULAR_SETTINGS["SECURITY"] and "SECURITY_DEFINITIONS"
# This module documents the pattern; actual wiring is in settings.py.


__all__ = [
    "ErrorResponseSerializer",
    "ErrorBodySerializer",
    "ErrorDetailSerializer",
    "COMMON_ERROR_RESPONSES",
]
