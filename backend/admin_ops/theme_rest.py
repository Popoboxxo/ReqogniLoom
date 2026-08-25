"""
admin_ops — REST adapter for Theme Presets (ThemePalette CRUD + export).

Endpoints (all under ``/api/v1/``):

    GET    /admin/theme-palettes/           any authenticated user
    POST   /admin/theme-palettes/           System-Admin only (import)
    GET    /admin/theme-palettes/<key>/export/   any authenticated user
    DELETE /admin/theme-palettes/<key>/     System-Admin only; ``is_system``
            rows always answer 403 regardless of role.

Permission pattern mirrors ``backend/admin_ops/banner_rest.py``:
``auth_tenancy.rest.HasOperationPermission`` with no ``required_operation``
(authenticated access is sufficient — the default ``RbacPermission`` would
lock out pure System-Admins whose ``active_roles`` is empty), plus the
explicit in-view gate ``ctx.has_role("admin") or
AuthorizationService().is_tenant_admin(...)`` for every write that is not
the caller's own preference. Error bodies use the standardized
``{"error": {code, message, details}}`` envelope via
:func:`rest_api.serializers.build_error_response`.
"""
from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_ops.models import (
    CANONICAL_COLOR_TOKEN_KEYS,
    MODE_DARK,
    MODE_LIGHT,
    TOKEN_KEYS_VERSION,
    TenantThemeDefault,
    ThemePalette,
    UserThemePreference,
)
from admin_ops.services.theme_service import ThemeService
from auth_tenancy.rest import HasOperationPermission
from auth_tenancy.services import AuthorizationService
from persistence.tenancy import TenantContext
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import build_error_response, detect_lang


def _is_system_admin(ctx) -> bool:
    """Same System-Admin check as GlobalBannerView / WorkspaceBannerView."""
    return ctx.has_role("admin") or AuthorizationService().is_tenant_admin(
        user_id=ctx.user_id, tenant_id=ctx.tenant_id
    )


def _err(code: str, lang: str, http_status: int, message: str | None = None) -> Response:
    return Response(
        build_error_response(code, lang, message=message),
        status=http_status,
    )


def _validate_tokens(dark_tokens: Any, light_tokens: Any, lang: str) -> Response | None:
    """A palette is all-or-nothing: both modes must carry exactly the
    canonical key set."""
    for name, tokens in (("dark_tokens", dark_tokens), ("light_tokens", light_tokens)):
        if not isinstance(tokens, dict):
            return _err(
                "VALIDATION_ERROR", lang, status.HTTP_400_BAD_REQUEST,
                message=f"{name} must be a JSON object.",
            )
        given = set(tokens.keys())
        missing = sorted(CANONICAL_COLOR_TOKEN_KEYS - given)
        extra = sorted(given - CANONICAL_COLOR_TOKEN_KEYS)
        if missing or extra:
            return _err(
                "VALIDATION_ERROR", lang, status.HTTP_400_BAD_REQUEST,
                message=f"{name}: missing={missing} extra={extra}",
            )
    return None


def _palette_to_dict(palette: ThemePalette) -> dict[str, Any]:
    return {
        "key": palette.key,
        "label": palette.label,
        "is_system": palette.is_system,
        "dark_tokens": palette.dark_tokens,
        "light_tokens": palette.light_tokens,
        "token_keys_version": palette.token_keys_version,
    }


class ThemePaletteListView(APIView):
    """``/api/v1/admin/theme-palettes/`` — GET: any user. POST: System-Admin."""

    permission_classes = [HasOperationPermission]

    def get(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return _err("AUTHENTICATION_REQUIRED", lang, status.HTTP_401_UNAUTHORIZED)
        TenantContext.set_tenant(ctx.tenant_id)
        # Lazy backfill so tenants created after the seed migration still see
        # the four stock palettes (see ThemeService docstring).
        ThemeService().ensure_system_palettes(ctx.tenant_id)
        palettes = ThemePalette.objects.all().order_by("key")
        return Response({"results": [_palette_to_dict(p) for p in palettes]})

    def post(self, request: Request, **kwargs: Any) -> Response:
        """Import a custom palette. System-Admin only; never importable as
        a system palette."""
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return _err("AUTHENTICATION_REQUIRED", lang, status.HTTP_401_UNAUTHORIZED)
        if not _is_system_admin(ctx):
            return _err("PERMISSION_DENIED", lang, status.HTTP_403_FORBIDDEN)

        TenantContext.set_tenant(ctx.tenant_id)

        error = _validate_tokens(
            request.data.get("dark_tokens", {}),
            request.data.get("light_tokens", {}),
            lang,
        )
        if error is not None:
            return error

        label = str(request.data.get("label", "")).strip()
        if not label:
            return _err(
                "VALIDATION_ERROR", lang, status.HTTP_400_BAD_REQUEST,
                message="label is required",
            )
        key = str(request.data.get("key") or label.lower().replace(" ", "-")).strip()
        if ThemePalette.objects.filter(key=key).exists():
            return _err(
                "VALIDATION_ERROR", lang, status.HTTP_400_BAD_REQUEST,
                message=f"A palette with key '{key}' already exists",
            )

        palette = ThemePalette.unscoped.create(
            tenant_id=ctx.tenant_id,
            key=key,
            label=label,
            is_system=False,
            dark_tokens=request.data.get("dark_tokens"),
            light_tokens=request.data.get("light_tokens"),
            token_keys_version=TOKEN_KEYS_VERSION,
            created_by_id=ctx.user_id,
        )
        return Response(_palette_to_dict(palette), status=status.HTTP_201_CREATED)


class ThemePaletteDetailView(APIView):
    """``/api/v1/admin/theme-palettes/<key>/`` — DELETE: System-Admin, and
    system palettes are read-only for everyone."""

    permission_classes = [HasOperationPermission]

    def delete(self, request: Request, key: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return _err("AUTHENTICATION_REQUIRED", lang, status.HTTP_401_UNAUTHORIZED)
        if not _is_system_admin(ctx):
            return _err("PERMISSION_DENIED", lang, status.HTTP_403_FORBIDDEN)

        TenantContext.set_tenant(ctx.tenant_id)
        ThemeService().ensure_system_palettes(ctx.tenant_id)
        palette = ThemePalette.objects.filter(key=key).first()
        if palette is None:
            return _err("NOT_FOUND", lang, status.HTTP_404_NOT_FOUND)
        if palette.is_system:
            return _err(
                "PERMISSION_DENIED", lang, status.HTTP_403_FORBIDDEN,
                message="System themes are read-only",
            )
        palette.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ThemePaletteExportView(APIView):
    """``GET /api/v1/admin/theme-palettes/<key>/export/`` — any authenticated
    user; returns the full palette payload (import-compatible)."""

    permission_classes = [HasOperationPermission]

    def get(self, request: Request, key: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return _err("AUTHENTICATION_REQUIRED", lang, status.HTTP_401_UNAUTHORIZED)
        TenantContext.set_tenant(ctx.tenant_id)
        ThemeService().ensure_system_palettes(ctx.tenant_id)
        palette = ThemePalette.objects.filter(key=key).first()
        if palette is None:
            return _err("NOT_FOUND", lang, status.HTTP_404_NOT_FOUND)
        return Response(_palette_to_dict(palette))


__all__ = [
    "TenantThemeDefaultView",
    "ThemePaletteDetailView",
    "ThemePaletteExportView",
    "ThemePaletteListView",
    "UserThemePreferenceView",
]


# ---------------------------------------------------------------------------
# Per-user preference + tenant-wide default (Task 4)
# ---------------------------------------------------------------------------


def _valid_mode(mode: Any) -> bool:
    return mode in (MODE_DARK, MODE_LIGHT)


class UserThemePreferenceView(APIView):
    """``/api/v1/users/me/theme-preference/`` — GET/PUT, always scoped to the
    authenticated caller. Any authenticated user may set their own."""

    permission_classes = [HasOperationPermission]

    def get(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return _err("AUTHENTICATION_REQUIRED", lang, status.HTTP_401_UNAUTHORIZED)
        TenantContext.set_tenant(ctx.tenant_id)
        pref = UserThemePreference.objects.filter(user_id=ctx.user_id).first()
        return Response(
            {
                "palette_key": pref.palette_key if pref else None,
                "mode": pref.mode if pref else None,
            }
        )

    def put(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return _err("AUTHENTICATION_REQUIRED", lang, status.HTTP_401_UNAUTHORIZED)

        mode = request.data.get("mode")
        if not _valid_mode(mode):
            return _err(
                "VALIDATION_ERROR", lang, status.HTTP_400_BAD_REQUEST,
                message="mode must be 'dark' or 'light'",
            )
        palette_key = request.data.get("palette_key")
        if palette_key is not None and not isinstance(palette_key, str):
            return _err(
                "VALIDATION_ERROR", lang, status.HTTP_400_BAD_REQUEST,
                message="palette_key must be a string or null",
            )

        TenantContext.set_tenant(ctx.tenant_id)
        UserThemePreference.unscoped.update_or_create(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            defaults={"palette_key": palette_key, "mode": mode},
        )
        return Response({"palette_key": palette_key, "mode": mode})


class TenantThemeDefaultView(APIView):
    """``/api/v1/system/theme-default/`` — GET: any authenticated user.
    PUT: System-Admin only; one row per tenant (upsert)."""

    permission_classes = [HasOperationPermission]

    def get(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return _err("AUTHENTICATION_REQUIRED", lang, status.HTTP_401_UNAUTHORIZED)
        TenantContext.set_tenant(ctx.tenant_id)
        default = TenantThemeDefault.objects.first()
        return Response(
            {
                "palette_key": default.palette_key if default else "default",
                "mode": default.mode if default else MODE_DARK,
            }
        )

    def put(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return _err("AUTHENTICATION_REQUIRED", lang, status.HTTP_401_UNAUTHORIZED)
        if not _is_system_admin(ctx):
            return _err("PERMISSION_DENIED", lang, status.HTTP_403_FORBIDDEN)

        mode = request.data.get("mode")
        if not _valid_mode(mode):
            return _err(
                "VALIDATION_ERROR", lang, status.HTTP_400_BAD_REQUEST,
                message="mode must be 'dark' or 'light'",
            )
        palette_key = request.data.get("palette_key")
        if not isinstance(palette_key, str) or not palette_key.strip():
            return _err(
                "VALIDATION_ERROR", lang, status.HTTP_400_BAD_REQUEST,
                message="palette_key is required",
            )

        TenantContext.set_tenant(ctx.tenant_id)
        TenantThemeDefault.unscoped.update_or_create(
            tenant_id=ctx.tenant_id,
            defaults={"palette_key": palette_key, "mode": mode},
        )
        return Response({"palette_key": palette_key, "mode": mode})
