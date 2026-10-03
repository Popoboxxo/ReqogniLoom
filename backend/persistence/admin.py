"""
Django admin registration for the persistence app (REQ-L1-010).

Registers the custom User model (REQ-L1-010) plus all 13 domain entities so
operators can inspect, search and edit them through the standard Django admin
site.  The admin site authenticates against AUTH_USER_MODEL = "persistence.User",
so staff users with is_staff=True can log in at /admin/ with their ReqFlow
credentials.

Tenant isolation (SEC-04, ADR-011):
    Every ``TenantScopedModel`` registration inherits
    ``TenantScopedAdminMixin``, so ``get_queryset`` and the per-object
    ``has_*_permission`` checks are narrowed to the requesting staff user's
    tenant (``request.user.tenant_id``). A staff user of tenant A can neither
    list nor change tenant B's rows; an operator without a tenant sees nothing.

    ``Role`` inherits ``tenant_lookup = 'id'`` because the ``Role`` model is
    scoped through its ``tenant`` FK to the root ``Tenant`` row (a tenant admin
    legitimately sees/edits the roles of its own tenant). ``Tenant`` itself is
    the root identity and is filtered on ``id``; ``User`` is filtered on the
    ``tenant`` FK. This replaces the previous ``unscoped()`` override, which
    deliberately showed every tenant's rows.

Read-only models:
    ``AuditLogEntry`` is append-only (REQ-L1-011) and the admin is locked
    down to read-only via the three ``has_*_permission`` overrides.
"""
from __future__ import annotations

from django.contrib import admin
from django.contrib.auth import get_user_model

from persistence.tenant_admin import TenantScopedAdminMixin

from .models import (
    ArchitectureElement,
    Artifact,
    AuditLogEntry,
    Requirement,
    Role,
    Tenant,
    TestCase,
    TestRun,
    TestRunResult,
    TraceLink,
    Workspace,
    StakeholderNeed,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# User — AUTH_USER_MODEL (already registered, kept here for completeness)
# ---------------------------------------------------------------------------


@admin.register(User)
class ReqogniLoomUserAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin view for the ReqFlow User model.

    Uses a tailored ModelAdmin (not django.contrib.auth.admin.UserAdmin)
    because persistence.User has a different field set than AbstractUser
    (UUID pk, tenant FK, no groups/permissions tables, no last_login/
    date_joined).

    Tenant-scoped on the ``tenant`` FK: an operator only manages the users of
    its own tenant.
    """

    list_display = (
        "username",
        "email",
        "is_active",
        "is_staff",
        "is_superuser",
        "tenant",
    )
    list_filter = ("is_active", "is_staff", "is_superuser", "tenant")
    search_fields = ("username", "email")
    ordering = ("username",)

    fieldsets = (
        (None, {"fields": ("username", "email", "password")}),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser")},
        ),
        (
            "Tenant",
            {"fields": ("tenant",)},
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "email",
                    "password",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "tenant",
                ),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        """Hash the password via set_password when it changes in admin."""
        if "password" in form.changed_data and form.cleaned_data.get("password"):
            obj.set_password(form.cleaned_data["password"])
        super().save_model(request, obj, form, change)


# ---------------------------------------------------------------------------
# Tenant — root identity (no tenant FK on itself, default manager is correct)
# ---------------------------------------------------------------------------


@admin.register(Tenant)
class TenantAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin view for the Tenant root identity (REQ-L1-008).

    The root model carries no ``tenant_id`` column of its own, so the mixin is
    pointed at ``id``: an operator sees only its own tenant row, not every
    tenant in the deployment.
    """

    tenant_lookup = "id"

    list_display = ("name", "slug", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    ordering = ("name",)
    readonly_fields = ("created_at", "created_by", "modified_at", "modified_by", "version")


# ---------------------------------------------------------------------------
# Tenant-scoped entities — TenantScopedAdminMixin narrows get_queryset to the
# operator's tenant (SEC-04, ADR-011)
# ---------------------------------------------------------------------------


@admin.register(Role)
class RoleAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin view for RBAC Role (REQ-L1-010).

    Tenant-scoped through the ``tenant`` FK. The mixin's ``tenant_lookup`` is
    pointed at ``id`` on the ``Tenant`` model, not here: ``Role`` carries its
    own ``tenant`` FK, so the default ``tenant_lookup = 'tenant_id'`` applies.
    """

    list_display = ("name", "tenant", "created_at")
    list_filter = ("tenant",)
    search_fields = ("name",)
    ordering = ("name",)
    readonly_fields = ("created_at", "created_by", "modified_at", "modified_by", "version")


@admin.register(Workspace)
class WorkspaceAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin view for Workspace (REQ-L1-008, REQ-L1-042)."""

    list_display = ("name", "tenant", "is_active", "closed_at", "created_at")
    list_filter = ("tenant", "is_active")
    search_fields = ("name",)
    ordering = ("name",)
    readonly_fields = ("created_at", "created_by", "modified_at", "modified_by", "version")


@admin.register(Artifact)
class ArtifactAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin view for Artifact (REQ-L1-001)."""

    list_display = ("id", "artifact_type", "workspace", "parent", "tenant", "created_at")
    list_filter = ("tenant", "artifact_type")
    search_fields = ("id", "artifact_type")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "created_by", "modified_at", "modified_by", "version")


@admin.register(Requirement)
class RequirementAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin view for Requirement (REQ-L1-001)."""

    list_display = ("title", "category", "tenant", "created_at")
    list_filter = ("tenant", "category")
    search_fields = ("title", "description")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "created_by", "modified_at", "modified_by", "version")


@admin.register(StakeholderNeed)
class StakeholderNeedAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin view for Stakeholder Need."""

    list_display = ("title", "category", "tenant", "moscow_priority", "created_at")
    list_filter = ("tenant", "category", "moscow_priority")
    search_fields = ("title", "description")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "created_by", "modified_at", "modified_by", "version")


@admin.register(ArchitectureElement)
class ArchitectureElementAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin view for ArchitectureElement (REQ-L1-002)."""

    list_display = ("title", "element_type", "tenant", "created_at")
    list_filter = ("tenant", "element_type")
    search_fields = ("title", "description")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "created_by", "modified_at", "modified_by", "version")


@admin.register(TraceLink)
class TraceLinkAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin view for TraceLink (REQ-L1-003)."""

    list_display = ("id", "link_type", "source", "target", "tenant", "created_at")
    list_filter = ("tenant", "link_type")
    search_fields = ("id", "link_type")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "created_by", "modified_at", "modified_by", "version")


@admin.register(TestCase)
class TestCaseAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin view for TestCase (REQ-L1-012)."""

    list_display = ("title", "tenant", "created_at")
    list_filter = ("tenant",)
    search_fields = ("title", "description")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "created_by", "modified_at", "modified_by", "version")


# ---------------------------------------------------------------------------
# AuditLogEntry — append-only, read-only in admin
# ---------------------------------------------------------------------------


@admin.register(AuditLogEntry)
class AuditLogEntryAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin view for the append-only AuditLogEntry (REQ-L1-011).

    The model is append-only (REQ-L1-011, ADR-10) so all write/delete
    permissions are denied.  Read access remains so operators can audit
    history through the standard admin UI — narrowed to their own tenant.
    """

    list_display = ("action", "object_type", "object_id", "actor", "tenant", "created_at")
    list_filter = ("tenant", "action", "object_type")
    search_fields = ("object_type", "object_id", "action")
    ordering = ("-created_at",)
    readonly_fields = (
        "action",
        "object_type",
        "object_id",
        "actor",
        "payload",
        "created_at",
        "created_by",
        "modified_at",
        "modified_by",
        "version",
        "tenant",
    )

    def has_add_permission(self, request):
        return False  # read-only

    def has_change_permission(self, request, obj=None):
        return False  # read-only

    def has_delete_permission(self, request, obj=None):
        return False  # read-only


# ---------------------------------------------------------------------------
# TestRun / TestRunResult — operational records
# ---------------------------------------------------------------------------


@admin.register(TestRun)
class TestRunAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin view for TestRun (REQ-L2-AS-030)."""

    list_display = ("name", "status", "workspace", "started_at", "finished_at", "tenant")
    list_filter = ("tenant", "status", "workspace")
    search_fields = ("name", "ci_job_id")
    ordering = ("-started_at",)
    readonly_fields = ("created_at", "created_by", "modified_at", "modified_by", "version")


@admin.register(TestRunResult)
class TestRunResultAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin view for TestRunResult (REQ-L2-AS-030)."""

    list_display = (
        "test_case_title",
        "status",
        "test_run",
        "executed_at",
        "duration_ms",
        "tenant",
    )
    list_filter = ("tenant", "status", "test_run")
    search_fields = ("test_case_title", "message")
    ordering = ("-executed_at",)
    readonly_fields = ("created_at", "created_by", "modified_at", "modified_by", "version")
