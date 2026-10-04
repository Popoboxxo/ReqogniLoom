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

INT-06 (systemaudit 2026-09, findings 075/077/090):
  - ``ErrorBodySerializer`` documents ``request_id`` (ADR-014 §1, REQ-071).
  - :func:`enforce_common_error_responses` is a drf-spectacular
    *postprocessing hook* (registered via ``SPECTACULAR_SETTINGS``) that injects
    :data:`COMMON_ERROR_RESPONSES` into every operation. Before this hook,
    ``COMMON_ERROR_RESPONSES`` was a *dead declaration*: 432 of 439 operations
    declared no error case at all, so a generated client could not build error
    handling from the contract (finding 075).
  - ``cookieAuth`` (auto-generated from ``SessionAuthentication``) was declared
    by zero operations — a dead auth path (finding 090). The hook drops any
    declared-but-unreferenced security scheme so the contract does not
    advertise an auth route that does not exist.
"""
from __future__ import annotations

from typing import Any

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
    """Schema for the inner error object.

    ADR-014 §1 / REQ-071: every error carries a machine-readable ``code``, a
    localized ``message``, an optional ``details`` list and a ``request_id``
    that mirrors the ``X-Request-ID`` response header (the correlation id
    already emitted by ``reqogniloom.middleware.RequestIdMiddleware``).
    """

    code = serializers.CharField(help_text="Machine-readable error code.")
    message = serializers.CharField(help_text="Human-readable localized message.")
    details = ErrorDetailSerializer(many=True, required=False)
    request_id = serializers.CharField(
        required=False,
        allow_null=True,
        help_text=(
            "Correlation id, mirrored from the X-Request-ID response header "
            "(ADR-014 §1)."
        ),
    )


class ErrorResponseSerializer(serializers.Serializer):
    """Standard error response shape (REQ-L2-RA-009).

    Format: {"error": {"code": "...", "message": "...", "details": [...],
    "request_id": "..."}}
    """

    error = ErrorBodySerializer()


# ---------------------------------------------------------------------------
# Common OpenAPI responses for use in extend_schema decorators
# ---------------------------------------------------------------------------

#: HTTP statuses with a well-known, uniform error body across the API. The
#: postprocessing hook below injects these into every operation so the
#: published contract is complete (finding 075). ``401`` is included even
#: though a handful of public endpoints (login/refresh/banners) genuinely
#: answer anonymously: DRF still answers a present-but-invalid credential on
#: those routes with 401, and the response *body* shape is identical. ``405``
#: and ``415`` complete the set DRF raises on its own with the canonical
#: envelope (``rest_api/error_envelope._STATUS_TO_CODE``).
COMMON_ERROR_RESPONSES = {
    400: OpenApiResponse(
        response=ErrorResponseSerializer,
        description="Validation error.",
        examples=[
            OpenApiExample(
                "ValidationError",
                value={
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Validation failed.",
                        "details": [],
                        "request_id": "3f1c…",
                    }
                },
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
# drf-spectacular POSTPROCESSING_HOOK — wire the common error responses and
# drop dead security schemes (findings 075 / 090).
# ---------------------------------------------------------------------------


def enforce_common_error_responses(
    result: dict[str, Any], generator: Any, request: Any, public: bool
) -> dict[str, Any]:
    """Inject the common error responses into every operation (finding 075).

    ``COMMON_ERROR_RESPONSES`` was declared but never referenced, so almost no
    operation carried an error case in the generated document. Rather than
    annotating hundreds of views individually (and re-annotating every new
    one), this postprocessing hook adds the missing responses to every
    operation that does not already declare them. An operation that already
    declares a status keeps its own, more specific response — the hook is
    purely additive.

    It also drops a declared-but-unreferenced ``cookieAuth`` security scheme
    (finding 090): the scheme is auto-generated from ``SessionAuthentication``
    but referenced by no operation, so the contract would otherwise advertise
    an auth route that does not exist.
    """
    for path_item in result.get("paths", {}).values():
        for operation in path_item.values():
            if not isinstance(operation, dict) or "responses" not in operation:
                continue
            responses = operation["responses"]
            for status_code, response in COMMON_ERROR_RESPONSES.items():
                key = str(status_code)
                # Do not overwrite a view's own, more specific declaration.
                responses.setdefault(key, _serialize_response(response))

    _drop_dead_security_schemes(result)
    return result


def _serialize_response(response: OpenApiResponse) -> dict[str, Any]:
    """Render an :class:`OpenApiResponse` to its OpenAPI response-object form.

    The shared :data:`COMMON_ERROR_RESPONSES` entries are ``OpenApiResponse``
    objects (the type ``extend_schema`` accepts per-operation). At
    postprocessing time the document is past the per-operation resolution, so
    the serializer is mapped to its component ``$ref`` here — the same
    serializer→schema conversion the generator performs for a decorated view.
    """
    from drf_spectacular.openapi import AutoSchema

    schema = AutoSchema()
    try:
        component = schema._map_serializer(
            response.response,  # type: ignore[arg-type]
            direction="response",
            bypass_extensions=False,
        )
    except Exception:  # pragma: no cover - defensive fallback
        # The error body component name is stable and public (it is exported
        # in __all__ and referenced by auth_views), so a fallback ref keeps the
        # document valid even if a future drf-spectacular changes the private
        # mapping API.
        component = {"$ref": "#/components/schemas/ErrorResponse"}
    return {
        "description": response.description or "",
        "content": {"application/json": {"schema": component}},
    }


def _drop_dead_security_schemes(result: dict[str, Any]) -> None:
    """Remove ``securitySchemes`` no operation references (finding 090)."""
    schemes = (
        result.get("components", {}).get("securitySchemes", {})
    )
    if not schemes:
        return

    referenced: set[str] = set()
    # Global scheme (SPECTACULAR_SETTINGS["SECURITY"]) counts as referenced.
    for requirement in result.get("security", []) or []:
        if isinstance(requirement, dict):
            referenced.update(requirement.keys())
    for path_item in result.get("paths", {}).values():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            for requirement in operation.get("security", []) or []:
                if isinstance(requirement, dict):
                    referenced.update(requirement.keys())

    for name in list(schemes):
        if name not in referenced:
            del schemes[name]


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
    "enforce_common_error_responses",
]
