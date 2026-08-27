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
        GET: System-Admin (``ctx.has_role("admin") or
        AuthorizationService().is_tenant_admin(...)`` — same pattern as
        ``TenantThemeDefaultView``) and returns the effective configuration
        (DB override from ``SystemMemorySettings`` falling back to env vars
        per field, see :func:`_with_env_fallback`).
        PUT: **Django superuser only** (:func:`_is_superuser`) — the write
        target is a deployment-global, cross-tenant row, which a merely
        workspace-scoped admin must not be able to change (final
        whole-branch review C-1). Applies a partial override (Memory Admin
        UI Phase 3, spec 2026-08-26). Delegates to
        :class:`application.memory_settings_service.MemorySettingsService`.
    POST /api/v1/system/memory-settings/reset/
        Django superuser only (same rationale as PUT). Clears every override
        field back to NULL, so the effective configuration falls back
        entirely to env vars. See :class:`SystemMemorySettingsResetView`.
    GET /api/v1/system/memory/workspaces/
        System-Admin only. Lists one overview row per workspace in the
        active tenant. Delegates to
        :meth:`application.memory_admin_service.MemoryAdminService.list_workspace_overview`.
    DELETE /api/v1/system/memory/workspaces/<uuid:workspace_id>/
        System-Admin only. Deletes both memory tiers for a workspace.
        Delegates to
        :meth:`application.memory_admin_service.MemoryAdminService.delete_workspace_memory`.
    GET /api/v1/system/memory/entries/
        System-Admin only (Memory Admin UI Phase 5, spec 2026-08-26).
        Paginated, full-text-filterable list of live consolidated memory
        entries across both tiers. See :class:`SystemMemoryEntriesListView`.
    GET /api/v1/system/memory/projection/
        System-Admin only (Memory Admin UI Phase 5). 2D PCA projection +
        similarity clustering of the scoped embedding vectors. See
        :class:`SystemMemoryProjectionView`.
    GET/DELETE /api/v1/memory/me/
        Any authenticated user, no role required (Memory Admin UI Phase 4,
        spec 2026-08-26). Self-service over the caller's OWN
        ``UserTenantMemory`` rows only — never ``WorkspaceMemory``. See
        :class:`MemorySelfServiceView`.

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
from uuid import UUID

from django.db.models import Count, Max
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.memory_admin_service import MemoryAdminService
from application.memory_settings_service import MemorySettingsService
from auth_tenancy.rest import HasOperationPermission
from auth_tenancy.services import AuthorizationService
from memory.models import UserTenantMemory, WorkspaceMemorySettings
from persistence.models import User
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import build_error_response, detect_lang


def _is_system_admin(ctx) -> bool:
    """True tenant-admin only — READ-side gate for ``SystemMemorySettingsView``.

    Tightened per a 5-phase Memory Admin UI review: this endpoint carries no
    ``workspace_id``, so the previous ``ctx.has_role("admin") or ...`` form
    let a caller who is merely admin of ONE workspace through — ``has_role``
    resolves from the tenant-wide UNION of the caller's ``UserRole`` rows
    when no workspace is in scope. That let a workspace-scoped admin read
    the deployment-global effective config (embedding provider/model,
    ollama_base_url, whether a Honcho API key is set) for every tenant, the
    exact class of over-broad access :func:`_is_superuser`'s docstring
    already calls out for the write side. Now matches the same
    tenant-admin-only bar every sibling System-Admin endpoint in this file
    uses (``MemoryAdminService._assert_system_admin``, Phase 1/5). Deliberately
    NOT used for the write side of ``/api/v1/system/memory-settings/`` — see
    :func:`_is_superuser`, which requires Django superuser, stricter still.
    """
    return AuthorizationService().is_tenant_admin(
        user_id=ctx.user_id, tenant_id=ctx.tenant_id
    )


def _is_superuser(user_id) -> bool:
    """Return whether *user_id* belongs to a Django superuser.

    Write gate for the deployment-global ``SystemMemorySettings`` singleton.
    :func:`_is_system_admin` is NOT sufficient here: this endpoint carries no
    ``workspace_id``, so ``ctx.has_role("admin")`` resolves from the
    tenant-wide UNION of the caller's ``UserRole`` rows — a merely
    workspace-scoped admin passes it. The row written here is process-global
    and shared by every tenant (it can, for instance, redirect all embedding
    traffic to an arbitrary ``ollama_base_url``), so a write needs a
    deployment-level identity, not a tenant/workspace one.

    Local copy of ``mcp_server.tools.users.UserTools._caller_is_superuser``
    (same semantics, same best-effort ``except`` policy) rather than an
    import: ``memory`` has no dependency on ``mcp_server`` today and a Layer-3
    app should not start importing another Layer-3 app for three lines.
    """
    try:
        user = User.objects.filter(id=user_id).first()
    except Exception:  # noqa: BLE001 - a lookup failure must never grant access
        return False
    return bool(user and user.is_superuser)


class SystemMemorySettingsWriteSerializer(serializers.Serializer):
    """Partial-update payload for ``PUT /api/v1/system/memory-settings/``."""

    # "openai" is a registered, documented provider (see llm_adapter.
    # embedding_service's module docstring: existing 1536-dim deployments are
    # told to keep EMBEDDING_PROVIDER=openai) — it must be selectable here,
    # otherwise such a deployment cannot even re-affirm its own configuration.
    embedding_provider = serializers.ChoiceField(
        choices=["sentence-transformers", "ollama", "openai", "mock"], required=False, allow_null=True
    )
    embedding_model_name = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=128)
    ollama_base_url = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=255)
    embedding_timeout = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    # "honcho" is selectable again: memory.honcho_backend now implements the
    # full MemoryBackend contract against the verified honcho-ai SDK and is
    # registered at startup via memory.apps.MemoryConfig.ready(), so
    # get_memory_backend() resolves it instead of raising. It still requires
    # HONCHO_BASE_URL (or the honcho_base_url override below) to be set —
    # that is surfaced as a health-check failure, not a save-time error, so an
    # admin can configure the URL and the backend in either order.
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
    """``/api/v1/system/memory-settings/`` — GET System-Admin, PUT superuser.

    GET returns the effective configuration (SystemMemorySettings DB
    override, falling back to env vars per field) plus an
    ``<field>_is_override`` flag per field so the UI can show what deviates
    from the default (Memory Admin UI Phase 3, spec 2026-08-26). PUT applies
    a partial override (Django superuser only, see :func:`_is_superuser`);
    omitted fields are left unchanged, a field sent as ``null`` (or, for the
    free-text fields, as ``""``) clears that field's override back to env.
    A response ``warning``
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
        if not _is_superuser(ctx.user_id):
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
        result = MemorySettingsService().update_settings(
            dict(ser.validated_data), user_id=ctx.user_id
        )
        return Response(_with_env_fallback(result))


class SystemMemorySettingsResetView(APIView):
    """``POST /api/v1/system/memory-settings/reset/`` — superuser only.

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
        if not _is_superuser(ctx.user_id):
            return Response(
                build_error_response("PERMISSION_DENIED", lang),
                status=status.HTTP_403_FORBIDDEN,
            )
        result = MemorySettingsService().reset_settings(user_id=ctx.user_id)
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


class _SystemMemoryVisualizationView(APIView):
    """Shared scope/workspace_id query-param parsing for the Phase 5 views.

    Both subclasses are System-Admin gated INSIDE ``MemoryAdminService`` via
    ``_assert_system_admin`` (Phase 5 plan Ruling 3) — deliberately not via
    the older, view-level :func:`_is_system_admin` helper that
    ``SystemMemorySettingsView`` still uses. ``permission_classes`` /
    no ``required_operation`` mirrors ``SystemMemoryWorkspaceOverviewView``:
    the default ``RbacPermission`` would deny a pure System-Admin outright on
    a URL that carries no ``workspace_id`` kwarg.
    """

    permission_classes = [HasOperationPermission]

    @staticmethod
    def _parse_scope_params(request: Request) -> tuple[str, Any]:
        """Return ``(scope, workspace_id)``.

        Raises :class:`ValidationError` for a malformed ``workspace_id``; an
        absent or unknown ``scope`` is left to the service, which owns the
        scope vocabulary and raises the same exception type.
        """
        scope = request.query_params.get("scope", "")
        raw_workspace_id = request.query_params.get("workspace_id") or None
        workspace_id = None
        if raw_workspace_id is not None:
            try:
                workspace_id = UUID(raw_workspace_id)
            except (ValueError, AttributeError, TypeError) as exc:
                raise ValidationError(f"Invalid workspace_id: {raw_workspace_id!r}") from exc
        return scope, workspace_id


class SystemMemoryEntriesListView(_SystemMemoryVisualizationView):
    """``GET /api/v1/system/memory/entries/`` — System-Admin only.

    Memory Admin UI Phase 5 (spec 2026-08-26). Query params: ``scope``
    (``workspace``|``global``), ``workspace_id`` (required for
    ``scope=workspace``), ``page`` (1-indexed), ``page_size``, ``q``
    (case-insensitive substring filter on ``content``). Returns
    ``{results, count, page, page_size}``.
    """

    #: Upper bound on ``page_size`` — this endpoint merges two tiers in
    #: Python, so an unbounded page size would be a trivial memory amplifier.
    MAX_PAGE_SIZE = 200

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
            scope, workspace_id = self._parse_scope_params(request)
            page = int(request.query_params.get("page", 1))
            page_size = int(request.query_params.get("page_size", 25))
        except ValidationError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        except (TypeError, ValueError):
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message="page and page_size must be integers."
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        page = max(1, page)
        page_size = max(1, min(page_size, self.MAX_PAGE_SIZE))
        q = (request.query_params.get("q") or "").strip() or None

        try:
            result = MemoryAdminService().list_entries(
                ctx, scope=scope, workspace_id=workspace_id, page=page, page_size=page_size, q=q
            )
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
        except ValidationError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(result)


class SystemMemoryProjectionView(_SystemMemoryVisualizationView):
    """``GET /api/v1/system/memory/projection/`` — System-Admin only.

    Memory Admin UI Phase 5 (spec 2026-08-26). Query params: ``scope``
    (``workspace``|``global``), ``workspace_id`` (required for
    ``scope=workspace``). Returns ``{points, sampled, sample_size,
    total_size, excluded_no_embedding}``; the heavy numeric work (PCA +
    clustering) happens in the service and is Redis-cached there.
    """

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
            scope, workspace_id = self._parse_scope_params(request)
            result = MemoryAdminService().get_projection(
                ctx, scope=scope, workspace_id=workspace_id
            )
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
        except ValidationError as exc:
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(result)


class MemorySelfServiceView(APIView):
    """``/api/v1/memory/me/`` — any authenticated user, no role required.

    Memory Admin UI Phase 4 (spec 2026-08-26). Self-service over the
    caller's OWN ``UserTenantMemory`` rows only — never ``WorkspaceMemory``,
    which is team-owned (see plan Ruling 1). No admin gate: the ``user_id``
    filter on every query IS the authorization boundary, mirroring
    ``ApiKeyViewSet``'s own-data-only self-service pattern.

    GET: ``{"entry_count": int, "last_updated_at": str | None}``.
    DELETE: deletes all of the caller's ``UserTenantMemory`` rows, returns
    ``{"deleted": int}`` — 200 even when nothing existed to delete.
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
        agg = UserTenantMemory.objects.filter(user_id=ctx.user_id).aggregate(
            count=Count("id"), last=Max("created_at")
        )
        return Response(
            {
                "entry_count": agg["count"] or 0,
                "last_updated_at": agg["last"],
            }
        )

    def delete(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
        except Exception:
            return Response(
                build_error_response("AUTHENTICATION_REQUIRED", lang),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        deleted, _ = UserTenantMemory.objects.filter(user_id=ctx.user_id).delete()
        return Response({"deleted": deleted})


__all__ = [
    "SystemMemorySettingsView",
    "SystemMemorySettingsResetView",
    "WorkspaceMemorySettingsView",
    "SystemMemoryWorkspaceOverviewView",
    "SystemMemoryWorkspaceDeleteView",
    "SystemMemoryEntriesListView",
    "SystemMemoryProjectionView",
    "MemorySelfServiceView",
]
