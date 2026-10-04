"""
Django admin registration for the auth_tenancy app (COMP-AT-001/002/005).

Registers:

* :class:`ApiKey` — hashed API-key credential (COMP-AT-001, REQ-L3-AT001-002/003)
* :class:`UserRole` — workspace-scoped RBAC role assignment (COMP-AT-002)
* :class:`ItemPermission` — item-level RBAC rule (COMP-AT-005, REQ-L1-039)
* :class:`UserWorkspacePreference` — per-user visibility override (REQ-L1-027)

Tenant isolation (SEC-04, ADR-011):
    The admin is a tenant-scoped surface. Each registration inherits
    ``TenantScopedAdminMixin``, so ``get_queryset`` and the per-object
    ``has_*_permission`` checks are narrowed to the requesting staff user's
    tenant (``request.user.tenant_id``). A staff user of tenant A can neither
    list nor change tenant B's rows; an operator without a tenant sees nothing.

Key material:
    ``ApiKey.key_hash`` is the credential. It is excluded from the admin form
    (not merely read-only) and removed from the search fields so it can neither
    be read nor pivoted on. The admin is not a key-creation path — creation
    goes through ``AuthenticationService`` (plaintext shown once) — so add is
    disabled.
"""
from __future__ import annotations

from django.contrib import admin

from persistence.tenant_admin import TenantScopedAdminMixin

from .models import ApiKey, ItemPermission, UserRole, UserWorkspacePreference


@admin.register(ApiKey)
class ApiKeyAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin view for ApiKey (COMP-AT-001, REQ-L3-AT001-002/003)."""

    list_display = ("name", "user", "tenant", "revoked_at", "last_used_at")
    list_filter = ("revoked_at",)
    # ``key_hash`` is deliberately absent: the admin must not expose or search
    # the credential material (SEC-04).
    search_fields = ("name", "user__username")
    ordering = ("-last_used_at",)
    readonly_fields = ("created_at", "created_by", "modified_at", "modified_by", "version")
    # Excluded (not read-only) so the hash is never rendered in the form.
    exclude = ("key_hash",)

    def has_add_permission(self, request):
        # API keys are only ever created through AuthenticationService, which
        # returns the plaintext exactly once. The admin must not become a
        # second creation path that stores an operator-chosen hash.
        return False


@admin.register(UserRole)
class UserRoleAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin view for UserRole (COMP-AT-002, REQ-L2-AT-006)."""

    list_display = ("user", "role", "workspace", "tenant", "suspended_at")
    list_filter = ("role", "workspace")
    search_fields = ("user__username", "user__email", "role")
    ordering = ("tenant", "user")
    readonly_fields = ("created_at", "created_by", "modified_at", "modified_by", "version")


@admin.register(ItemPermission)
class ItemPermissionAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin view for ItemPermission (COMP-AT-005, REQ-L1-039)."""

    list_display = (
        "user",
        "workspace",
        "artifact",
        "permission_level",
        "tenant",
        "granted_by",
    )
    list_filter = ("permission_level", "workspace")
    search_fields = ("user__username", "user__email")
    ordering = ("tenant", "workspace", "user")
    readonly_fields = ("created_at", "created_by", "modified_at", "modified_by", "version")


@admin.register(UserWorkspacePreference)
class UserWorkspacePreferenceAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin view for UserWorkspacePreference (REQ-L1-027)."""

    list_display = ("user", "workspace", "tenant")
    list_filter = ("workspace",)
    search_fields = ("user__username", "user__email")
    ordering = ("tenant", "workspace", "user")
    readonly_fields = ("created_at", "created_by", "modified_at", "modified_by", "version")
