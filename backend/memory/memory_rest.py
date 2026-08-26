"""
memory — REST adapter for Memory Settings (Spec 2026-08-24, Task 11) and
Memory Admin UI Phase 1 (Spec 2026-08-26).

Endpoints:
    GET/PUT /api/v1/workspaces/<uuid:workspace_id>/memory-settings/
        GET: any workspace member may view (missing row -> ``enabled: True``,
        the memory feature defaults ON, mirrors
        ``WorkspaceContextSettings``'s "missing row = default state"
        convention). PUT: editor or admin (workspace-scoped) may toggle.
    GET/PUT /api/v1/system/memory-settings/
        System-Admin only (``ctx.has_role("admin") or
        AuthorizationService().is_tenant_admin(...)`` — same pattern as
        ``TenantThemeDefaultView``). GET returns the effective configuration
        (DB override from ``SystemMemorySettings`` falling back to env vars
        per field, see :func:`_with_env_fallback`), PUT applies a partial
        override (Memory Admin UI Phase 3, spec 2026-08-26). Delegates to
        :class:`application.memory_settings_service.MemorySettingsService`.
    POST /api/v1/system/memory-settings/reset/
        System-Admin only. Clears every override field back to NULL, so the
        effective configuration falls back entirely to env vars. See
        :class:`SystemMemorySettingsResetView`.
    GET /api/v1/system/memory/workspaces/
        System-Admin only. Lists one overview row per workspace in the
        active tenant. Delegates to
        :meth:`application.memory_admin_service.MemoryAdminService.list_workspace_overview`.
    DELETE /api/v1/system/memory/workspaces/<uuid:workspace_id>/
        System-Admin only. Deletes both memory tiers for a workspace.
        Delegates to
        :meth:`application.memory_admin_service.MemoryAdminService.delete_workspace_memory`.

Both views rely on the tenant context already activated by
``AuthTenancyAuthentication`` during DRF authentication (COMP-AT-003
``TenantContextService.activate`` -> ``persistence.middleware.
set_request_tenant``) — mirrors ``rest_api.settings_views.
ContextGraphSettingsView``/``ReviewPolicyView``/``rest_api.preference_views.
UserPreferenceView``, none of which re-activate the tenant context
themselves. No bare ``persistence.tenancy.TenantContext.set_tenant(...)``
call appears anywhere in this module — that call only satisfies the
Django-ORM side and never arms Postgres RLS's ``app.current_tenant`` session
variable (the exact bug class already fixed in ``memory/backends.py``,
``llm_adapter/tasks.py`` and others); it is unnecessary here because a real
HTTP request already has both isolation layers armed by the time a view
method runs.
"""
from __future__ import annotations

from typing import Any

from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.base import NotFoundError, PermissionDeniedError
from application.memory_admin_service import MemoryAdminService
from application.memory_settings_service import MemorySettingsService
from auth_tenancy.rest import HasOperationPermission
from auth_tenancy.services import AuthorizationService
from memory.models import WorkspaceMemorySettings
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import build_error_response, detect_lang


def _is_system_admin(ctx) -> bool:
    """Same System-Admin check as GlobalBannerView / TenantThemeDefaultView."""
    return ctx.has_role("admin") or AuthorizationService().is_tenant_admin(
        user_id=ctx.user_id, tenant_id=ctx.tenant_id
    )


class SystemMemorySettingsWriteSerializer(serializers.Serializer):
    """Partial-update payload for ``PUT /api/v1/system/memory-settings/``."""

    embedding_provider = serializers.ChoiceField(
        choices=["sentence-transformers", "ollama", "mock"], required=False, allow_null=True
    )
    embedding_model_name = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=128)
    ollama_base_url = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=255)
    embedding_timeout = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    memory_backend = serializers.ChoiceField(
        choices=["pgvector", "honcho"], required=False, allow_null=True
    )
    honcho_base_url = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=255)
    honcho_api_key = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=512)


def _with_env_fallback(effective: dict) -> dict:
    """Fill in the env-var value for every field the DB override left None,
    so the response's top-level fields are always the ACTUAL effective
    configuration (override-or-env), not just the raw override row.
    """
    import os

    env_defaults = {
        "embedding_provider": os.environ.get("EMBEDDING_PROVIDER", "sentence-transformers"),
        "embedding_model_name": os.environ.get("EMBEDDING_MODEL_NAME"),
        "ollama_base_url": os.environ.get("OLLAMA_BASE_URL"),
        "embedding_timeout": int(os.environ.get("EMBEDDING_TIMEOUT", "10")),
        "memory_backend": os.environ.get("MEMORY_BACKEND", "pgvector"),
        "honcho_base_url": os.environ.get("HONCHO_BASE_URL"),
    }
    out = dict(effective)
    for field, env_value in env_defaults.items():
        if out.get(field) is None:
            out[field] = env_value
    return out


class WorkspaceMemorySettingsView(APIView):
    """``/api/v1/workspaces/<uuid:workspace_id>/memory-settings/``.

    GET: any workspace member. PUT: editor or admin (workspace-scoped).
    """

    def get(self, request: Request, workspace_id: str, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            get_auth_context(request)
        except Exception:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        # Workspace membership + READ permission is already enforced by the
        # default RbacPermission gate (rest_api.auth_enforcer): the URL
        # carries workspace_id, so AuthTenancyAuthentication resolves
        # active_roles scoped to THIS workspace, and a non-member (no
        # UserRole here) resolves to () -> denied 403 before this method
        # ever runs (mirrors WorkspaceBannerView's GET, see its docstring).
        settings_row = WorkspaceMemorySettings.objects.filter(workspace_id=workspace_id).first()
        return Response({"enabled": settings_row.enabled if settings_row else True})

    def put(self, request: Request, workspace_id: str, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        roles = AuthorizationService().active_roles_for(user_id=ctx.user_id, workspace_id=workspace_id)
        if "editor" not in roles and "admin" not in roles:
            return Response(
                build_error_response("PERMISSION_DENIED", lang),
                status=status.HTTP_403_FORBIDDEN,
            )

        enabled = request.data.get("enabled", True)
        if not isinstance(enabled, bool):
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message="Field 'enabled' must be a boolean."
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Explicit tenant_id (not relying on TenantManager.create()'s
        # auto-inject): update_or_create's create fallback goes through the
        # underlying QuerySet.create(), which bypasses the Manager-level
        # override, so tenant_id must be supplied here directly (same
        # pattern as TenantThemeDefaultView.put's unscoped.update_or_create).
        settings_row, _ = WorkspaceMemorySettings.objects.update_or_create(
            workspace_id=workspace_id,
            defaults={"enabled": enabled, "tenant_id": ctx.tenant_id},
        )
        return Response({"enabled": settings_row.enabled})


class SystemMemorySettingsView(APIView):
    """``/api/v1/system/memory-settings/`` — System-Admin only.

    GET returns the effective configuration (SystemMemorySettings DB
    override, falling back to env vars per field) plus an
    ``<field>_is_override`` flag per field so the UI can show what deviates
    from the default (Memory Admin UI Phase 3, spec 2026-08-26). PUT applies
    a partial override; omitted fields are left unchanged, a field sent as
    ``null`` clears that field's override back to env. A response ``warning``
    (non-null only when embedding_provider/memory_backend actually changed)
    tells the caller existing embeddings were not migrated automatically.

    ``permission_classes``/no ``required_operation`` mirrors
    ``TenantThemeDefaultView``/``GlobalBannerView``'s write side: the default
    ``RbacPermission`` (``rest_api.auth_enforcer``) would deny a pure
    System-Admin outright, because ``active_roles`` resolves to ``()`` for a
    caller with a tenant-wide ``TenantRole`` but no workspace-scoped
    ``UserRole`` (this endpoint targets no workspace). ``HasOperationPermission``
    with no declared operation only requires an authenticated caller, leaving
    the real System-Admin gate to :func:`_is_system_admin` below.
    """

    permission_classes = [HasOperationPermission]

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not _is_system_admin(ctx):
            return Response(
                build_error_response("PERMISSION_DENIED", lang),
                status=status.HTTP_403_FORBIDDEN,
            )
        effective = MemorySettingsService().get_effective_settings()
        return Response(_with_env_fallback(effective))

    def put(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not _is_system_admin(ctx):
            return Response(
                build_error_response("PERMISSION_DENIED", lang),
                status=status.HTTP_403_FORBIDDEN,
            )
        ser = SystemMemorySettingsWriteSerializer(data=request.data, partial=True)
        if not ser.is_valid():
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    details=[{"field": k, "errors": v} for k, v in ser.errors.items()],
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        result = MemorySettingsService().update_settings(dict(ser.validated_data))
        return Response(_with_env_fallback(result))


class SystemMemorySettingsResetView(APIView):
    """``POST /api/v1/system/memory-settings/reset/`` — System-Admin only.

    Clears every SystemMemorySettings override field back to NULL, so the
    effective configuration falls back entirely to environment variables.
    """

    permission_classes = [HasOperationPermission]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not _is_system_admin(ctx):
            return Response(
                build_error_response("PERMISSION_DENIED", lang),
                status=status.HTTP_403_FORBIDDEN,
            )
        result = MemorySettingsService().reset_settings()
        return Response(_with_env_fallback(result))


class SystemMemoryWorkspaceOverviewView(APIView):
    """``GET /api/v1/system/memory/workspaces/`` — System-Admin only.

    Memory Admin UI Phase 1 (spec 2026-08-26). Lists one row per workspace
    in the active tenant: memory enabled/disabled, entry counts per tier,
    last consolidation timestamp. Delegates to :class:`MemoryAdminService`.
    """

    permission_classes = [HasOperationPermission]

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            overview = MemoryAdminService().list_workspace_overview(ctx)
        except PermissionDeniedError:
            return Response(
                build_error_response("PERMISSION_DENIED", lang),
                status=status.HTTP_403_FORBIDDEN,
            )
        # MemoryAdminService returns raw uuid.UUID values (see its own
        # UUID-to-UUID comparisons in application/tests/test_memory_admin_
        # service.py) — since this view returns a plain dict (no
        # Serializer/UUIDField doing the to_representation coercion that
        # e.g. StakeholderNeedViewSet gets for free), stringify workspace_id
        # here so response.data matches the actual over-the-wire JSON shape
        # (DRF's JSONRenderer already encodes UUID as str on the real
        # response body; this keeps `response.data` consistent with that
        # for API consumers/tests inspecting it directly).
        for row in overview:
            row["workspace_id"] = str(row["workspace_id"])
        return Response({"results": overview})


class SystemMemoryWorkspaceDeleteView(APIView):
    """``DELETE /api/v1/system/memory/workspaces/<uuid:workspace_id>/``.

    System-Admin only. Deletes BOTH tiers: the workspace's own
    ``WorkspaceMemory`` rows and its current members' ``UserTenantMemory``
    rows. See :meth:`MemoryAdminService.delete_workspace_memory`.
    """

    permission_classes = [HasOperationPermission]

    def delete(self, request: Request, workspace_id: str, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            result = MemoryAdminService().delete_workspace_memory(ctx, workspace_id)
        except PermissionDeniedError:
            return Response(
                build_error_response("PERMISSION_DENIED", lang),
                status=status.HTTP_403_FORBIDDEN,
            )
        except NotFoundError as exc:
            return Response(
                build_error_response("NOT_FOUND", lang, message=str(exc)),
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(result)


__all__ = [
    "SystemMemorySettingsView",
    "SystemMemorySettingsResetView",
    "WorkspaceMemorySettingsView",
    "SystemMemoryWorkspaceOverviewView",
    "SystemMemoryWorkspaceDeleteView",
]
