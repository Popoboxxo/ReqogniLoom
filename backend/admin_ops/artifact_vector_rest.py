"""admin_ops — REST adapter for the artifact vector store configuration.

Endpoints:

    GET /api/v1/system/artifact-vector-settings/
        System-Admin only. Returns the effective configuration: the stored
        selector override, the resolved backend, every registered backend's
        schema/effective values/override flags, and the read-only diagnostic
        (requested/active/reason) the health surface also publishes.

    PUT /api/v1/system/artifact-vector-settings/
        Django superuser only (the row is deployment-global, mirroring
        ``/system/memory-settings/``). Partial update; ``vector_backend: null``
        clears the override so ``ARTIFACT_VECTOR_BACKEND`` wins again.

    POST /api/v1/system/artifact-vector-settings/reset/
        Django superuser only. Clears the selector and every backend override.

All business logic lives in
:class:`application.artifact_vector_settings_service.ArtifactVectorSettingsService`;
this module only gates, validates shape and transports.
"""
from __future__ import annotations

from typing import Any

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.artifact_vector_settings_service import (
    ArtifactVectorSettingsService,
    ArtifactVectorSettingsValidationError,
)
from auth_tenancy.rest import HasOperationPermission
from auth_tenancy.services import AuthorizationService
from persistence.models import User
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import build_error_response, detect_lang


def _is_system_admin(ctx: Any) -> bool:
    """Tenant-admin only READ gate (no workspace scope on this endpoint)."""
    return AuthorizationService().is_tenant_admin(
        user_id=ctx.user_id, tenant_id=ctx.tenant_id
    )


def _is_superuser(user_id: Any) -> bool:
    """Whether *user_id* is a Django superuser (deployment-level write gate)."""
    try:
        user = User.objects.filter(id=user_id).first()
    except Exception:  # noqa: BLE001 - a lookup failure must never grant access
        return False
    return bool(user and user.is_superuser)


class BackendSettingFieldSerializer(serializers.Serializer):
    name = serializers.CharField()
    type = serializers.CharField()
    env_var = serializers.CharField(allow_null=True, required=False)
    label_key = serializers.CharField(required=False)
    choices = serializers.ListField(child=serializers.CharField(), required=False)
    min_value = serializers.FloatField(allow_null=True, required=False)
    max_length = serializers.IntegerField(allow_null=True, required=False)
    default = serializers.JSONField(allow_null=True, required=False)


class VectorBackendPayloadSerializer(serializers.Serializer):
    schema = BackendSettingFieldSerializer(many=True)
    values = serializers.DictField()
    is_override = serializers.DictField(child=serializers.BooleanField())
    secrets_set = serializers.DictField(child=serializers.BooleanField())
    capabilities = serializers.DictField()


class ArtifactVectorSettingsResponseSerializer(serializers.Serializer):
    vector_backend = serializers.CharField(allow_null=True, required=False)
    vector_backend_is_override = serializers.BooleanField(required=False)
    effective_vector_backend = serializers.CharField()
    available_backends = serializers.ListField(child=serializers.CharField())
    backends = serializers.DictField(child=VectorBackendPayloadSerializer())
    diagnostic = serializers.DictField(child=serializers.CharField())


class ArtifactVectorSettingsWriteSerializer(serializers.Serializer):
    """Partial-update payload; field-level validation lives in the service."""

    vector_backend = serializers.CharField(
        required=False, allow_null=True, allow_blank=True
    )
    backend_options = serializers.DictField(required=False)
    backend_secrets = serializers.DictField(required=False)


class SystemArtifactVectorSettingsView(APIView):
    """``/api/v1/system/artifact-vector-settings/`` — GET System-Admin, PUT superuser."""

    permission_classes = [HasOperationPermission]

    @extend_schema(
        tags=["admin"],
        summary="Read the effective artifact vector-store configuration",
        responses={
            200: ArtifactVectorSettingsResponseSerializer,
            401: OpenApiResponse(description="No valid credential."),
            403: OpenApiResponse(description="Tenant-Admin role required."),
        },
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except NotAuthenticated:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not _is_system_admin(ctx):
            return Response(
                build_error_response("PERMISSION_DENIED", lang),
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(ArtifactVectorSettingsService().get_effective_settings())

    @extend_schema(
        tags=["admin"],
        summary="Apply a partial artifact vector-store override",
        request=ArtifactVectorSettingsWriteSerializer,
        responses={
            200: ArtifactVectorSettingsResponseSerializer,
            400: OpenApiResponse(description="Invalid override value."),
            401: OpenApiResponse(description="No valid credential."),
            403: OpenApiResponse(description="Django superuser required."),
        },
    )
    def put(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except NotAuthenticated:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not _is_superuser(ctx.user_id):
            return Response(
                build_error_response("PERMISSION_DENIED", lang),
                status=status.HTTP_403_FORBIDDEN,
            )
        ser = ArtifactVectorSettingsWriteSerializer(data=request.data, partial=True)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            result = ArtifactVectorSettingsService().update_settings(
                dict(ser.validated_data), user_id=ctx.user_id
            )
        except ArtifactVectorSettingsValidationError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, details=exc.details),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(result)


class SystemArtifactVectorSettingsResetView(APIView):
    """``POST /api/v1/system/artifact-vector-settings/reset/`` — superuser only."""

    permission_classes = [HasOperationPermission]

    @extend_schema(
        tags=["admin"],
        summary="Clear every artifact vector-store override (fall back to env)",
        request=None,
        responses={
            200: ArtifactVectorSettingsResponseSerializer,
            401: OpenApiResponse(description="No valid credential."),
            403: OpenApiResponse(description="Django superuser required."),
        },
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except NotAuthenticated:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not _is_superuser(ctx.user_id):
            return Response(
                build_error_response("PERMISSION_DENIED", lang),
                status=status.HTTP_403_FORBIDDEN,
            )
        result = ArtifactVectorSettingsService().reset_settings(user_id=ctx.user_id)
        return Response(result)
