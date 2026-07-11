"""
COMP-RA-001 — LLM configuration REST endpoints (REQ-L2-LLM-001).

Endpoints:
  GET   /api/v1/llm-settings/
      Return the active tenant's LLM configuration. The row is created on
      first access (get-or-create with provider=mock). ``api_key`` is never
      returned; a boolean ``api_key_is_set`` reports whether one is stored.

  PUT   /api/v1/llm-settings/
  PATCH /api/v1/llm-settings/
      Update the configuration. ``api_key`` is write-only.

Authentication: Bearer token (global default).
Permissions:    Admin role only (both read and write) — LLM credentials are
                sensitive tenant-wide configuration.
"""
from __future__ import annotations

from typing import Any

from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from auth_tenancy.models import ROLE_ADMIN
from persistence.models import LlmProvider, LlmSettings
from persistence.tenancy import TenantContext
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import build_error_response, detect_lang


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------


class LlmSettingsSerializer(serializers.Serializer):
    """Read/write serializer for :class:`LlmSettings` (REQ-L2-LLM-001).

    ``api_key`` is write-only: it is accepted on write but never serialized on
    read. Readers receive ``api_key_is_set`` instead, so the UI can render a
    "configured" indicator without ever exposing the secret.
    """

    provider = serializers.ChoiceField(choices=LlmProvider.values)
    base_url = serializers.URLField(required=False, allow_blank=True)
    model_name = serializers.CharField(
        required=False, allow_blank=True, max_length=255
    )
    api_key = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=512
    )
    api_key_is_set = serializers.SerializerMethodField()

    def get_api_key_is_set(self, obj: LlmSettings) -> bool:
        """Return whether a non-empty API key is stored."""
        return bool(getattr(obj, "api_key", ""))


# Fields that a client may write onto the model.
_WRITABLE_FIELDS = ("provider", "base_url", "model_name", "api_key")


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------


class LlmSettingsView(APIView):
    """GET/PUT/PATCH /api/v1/llm-settings/ (REQ-L2-LLM-001). Admin-only."""

    def _forbidden(self, lang: str) -> Response:
        return Response(
            build_error_response(
                "PERMISSION_DENIED",
                lang,
                message="Admin role required to access LLM settings.",
            ),
            status=status.HTTP_403_FORBIDDEN,
        )

    def _get_or_create(self, ctx: Any) -> LlmSettings:
        """Return the tenant's singleton LlmSettings row, creating it if absent."""
        TenantContext.set_tenant(ctx.tenant_id)
        obj, _ = LlmSettings.objects.get_or_create(
            tenant_id=ctx.tenant_id,
            defaults={"provider": LlmProvider.MOCK},
        )
        return obj

    # ---- GET ----------------------------------------------------------

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        if not ctx.has_role(ROLE_ADMIN):
            return self._forbidden(lang)
        obj = self._get_or_create(ctx)
        return Response(LlmSettingsSerializer(obj).data)

    # ---- PUT / PATCH --------------------------------------------------

    def put(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self._update(request, partial=False)

    def patch(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self._update(request, partial=True)

    def _update(self, request: Request, *, partial: bool) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        if not ctx.has_role(ROLE_ADMIN):
            return self._forbidden(lang)

        obj = self._get_or_create(ctx)
        ser = LlmSettingsSerializer(obj, data=request.data, partial=partial)
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

        for field in _WRITABLE_FIELDS:
            if field in ser.validated_data:
                setattr(obj, field, ser.validated_data[field])
        obj.save()
        return Response(LlmSettingsSerializer(obj).data)


__all__ = ["LlmSettingsView", "LlmSettingsSerializer"]
