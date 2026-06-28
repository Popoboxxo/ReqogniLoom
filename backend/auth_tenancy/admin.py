"""
Django admin registration for the auth_tenancy app (COMP-AT-001/002/005).

Registers:

* :class:`ApiKey` — hashed API-key credential (COMP-AT-001, REQ-L3-AT001-002/003)
* :class:`UserRole` — workspace-scoped RBAC role assignment (COMP-AT-002)
* :class:`ItemPermission` — item-level RBAC rule (COMP-AT-005, REQ-L1-039)
* :class:`UserWorkspacePreference` — per-user visibility override (REQ-L1-027)

Tenant isolation:
    All four inherit ``TenantScopedModel``. Each ``get_queryset`` uses the
    ``unscoped()`` manager so the admin surfaces rows across tenants for
    maintenance operations.
"""
from __future__ import annotations

from django.contrib import admin

from .models import ApiKey, ItemPermission, UserRole, UserWorkspacePreference


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    """Admin view for ApiKey (COMP-AT-001, REQ-L3-AT001-002/003)."""

    list_display = ("name", "user", "tenant", "revoked_at", "last_used_at")
    list_filter = ("tenant", "revoked_at")
    search_fields = ("name", "key_hash", "user__username")
    ordering = ("-last_used_at",)
    readonly_fields = ("key_hash", "created_at", "created_by", "modified_at", "modified_by", "version")

    def get_queryset(self, request):
        # CRITICAL: bypass the tenant-isolating default manager.
        return ApiKey.objects.unscoped()


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    """Admin view for UserRole (COMP-AT-002, REQ-L2-AT-006)."""

    list_display = ("user", "role", "workspace", "tenant", "suspended_at")
    list_filter = ("tenant", "role", "workspace")
    search_fields = ("user__username", "user__email", "role")
    ordering = ("tenant", "user")
    readonly_fields = ("created_at", "created_by", "modified_at", "modified_by", "version")

    def get_queryset(self, request):
        return UserRole.objects.unscoped()


@admin.register(ItemPermission)
class ItemPermissionAdmin(admin.ModelAdmin):
    """Admin view for ItemPermission (COMP-AT-005, REQ-L1-039)."""

    list_display = (
        "user",
        "workspace",
        "artifact",
        "permission_level",
        "tenant",
        "granted_by",
    )
    list_filter = ("tenant", "permission_level", "workspace")
    search_fields = ("user__username", "user__email")
    ordering = ("tenant", "workspace", "user")
    readonly_fields = ("created_at", "created_by", "modified_at", "modified_by", "version")

    def get_queryset(self, request):
        return ItemPermission.objects.unscoped()


@admin.register(UserWorkspacePreference)
class UserWorkspacePreferenceAdmin(admin.ModelAdmin):
    """Admin view for UserWorkspacePreference (REQ-L1-027)."""

    list_display = ("user", "workspace", "tenant")
    list_filter = ("tenant", "workspace")
    search_fields = ("user__username", "user__email")
    ordering = ("tenant", "workspace", "user")
    readonly_fields = ("created_at", "created_by", "modified_at", "modified_by", "version")

    def get_queryset(self, request):
        return UserWorkspacePreference.objects.unscoped()
