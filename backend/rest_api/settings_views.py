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

from application.settings_service import SettingsService
from auth_tenancy.models import ROLE_ADMIN
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

    provider = serializers.ChoiceField(choices=SettingsService.provider_choices())
    base_url = serializers.URLField(required=False, allow_blank=True)
    model_name = serializers.CharField(
        required=False, allow_blank=True, max_length=255
    )
    api_key = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=512
    )
    api_key_is_set = serializers.SerializerMethodField()

    def get_api_key_is_set(self, obj: Any) -> bool:
        """Return whether a non-empty API key is stored."""
        return bool(getattr(obj, "api_key", ""))


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

    # ---- GET ----------------------------------------------------------

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        if not ctx.has_role(ROLE_ADMIN):
            return self._forbidden(lang)
        obj = SettingsService().get_or_create_llm_settings(ctx)
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

        svc = SettingsService()
        obj = svc.get_or_create_llm_settings(ctx)
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

        obj = svc.update_llm_settings(ctx, dict(ser.validated_data))
        return Response(LlmSettingsSerializer(obj).data)


# ---------------------------------------------------------------------------
# PromptTemplate — tenant-scoped singleton LLM prompt templates (REQ-L2-PT-001)
# ---------------------------------------------------------------------------


class PromptTemplateSerializer(serializers.Serializer):
    """Read/write serializer for :class:`PromptTemplate` (REQ-L2-PT-001).

    All three slot fields are readable and writable. ``defaults_dict`` is a
    read-only map of slot name -> factory default, so the UI can offer a
    "reset to default" affordance without hard-coding the prompt text.
    """

    need_to_sysreq = serializers.CharField(
        required=False, allow_blank=True, trim_whitespace=False
    )
    sysreq_to_arch_assign = serializers.CharField(
        required=False, allow_blank=True, trim_whitespace=False
    )
    sysreq_decompose_next_level = serializers.CharField(
        required=False, allow_blank=True, trim_whitespace=False
    )
    defaults_dict = serializers.SerializerMethodField()

    def get_defaults_dict(self, obj: Any) -> dict:
        """Return the read-only factory defaults for every slot."""
        return SettingsService.prompt_defaults()


class PromptTemplateView(APIView):
    """GET/PUT/PATCH /api/v1/prompt-templates/ (REQ-L2-PT-001).

    Tenant-scoped singleton. Admin role required to read or write, mirroring
    :class:`LlmSettingsView` — prompt templates steer AI derivation and are
    tenant-wide configuration.
    """

    def _forbidden(self, lang: str) -> Response:
        return Response(
            build_error_response(
                "PERMISSION_DENIED",
                lang,
                message="Admin role required to access prompt templates.",
            ),
            status=status.HTTP_403_FORBIDDEN,
        )

    # ---- GET ----------------------------------------------------------

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        if not ctx.has_role(ROLE_ADMIN):
            return self._forbidden(lang)
        obj = SettingsService().get_or_create_prompt_template(ctx)
        return Response(PromptTemplateSerializer(obj).data)

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

        svc = SettingsService()
        obj = svc.get_or_create_prompt_template(ctx)
        ser = PromptTemplateSerializer(obj, data=request.data, partial=partial)
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

        obj = svc.update_prompt_template(ctx, dict(ser.validated_data))
        return Response(PromptTemplateSerializer(obj).data)


class PromptTemplateResetView(APIView):
    """POST /api/v1/prompt-templates/reset/ (REQ-L2-PT-001).

    Restore prompt content to the factory ``DEFAULT_*`` constants. Body may
    contain ``{"slot": "<name>"}`` to reset a single slot; without it, all
    slots are reset. Admin role required.
    """

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        if not ctx.has_role(ROLE_ADMIN):
            return Response(
                build_error_response(
                    "PERMISSION_DENIED",
                    lang,
                    message="Admin role required to reset prompt templates.",
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        svc = SettingsService()
        slot = request.data.get("slot")
        if slot is not None and not svc.is_valid_prompt_slot(slot):
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    message=f"Unknown prompt slot: '{slot}'.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        obj = svc.reset_prompt_template(ctx, slot=slot)
        return Response(PromptTemplateSerializer(obj).data)


__all__ = [
    "LlmSettingsView",
    "LlmSettingsSerializer",
    "PromptTemplateView",
    "PromptTemplateResetView",
    "PromptTemplateSerializer",
]
