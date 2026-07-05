"""
Django admin registration for the persistence app (REQ-L1-010).

Registers the custom User model (REQ-L1-010) plus all 13 domain entities so
operators can inspect, search and edit them through the standard Django admin
site.  The admin site authenticates against AUTH_USER_MODEL = "persistence.User",
so staff users with is_staff=True can log in at /admin/ with their ReqFlow
credentials.

Tenant isolation (ADR-03, REQ-L2-PL-001):
    Every ``TenantScopedModel`` registration overrides ``get_queryset`` to use
    the ``unscoped()`` manager.  The default ``objects`` manager applies a
    thread-local tenant filter, which is the right behaviour for the
    application but would HIDE rows from a human operator viewing the admin —
    the admin is a cross-tenant maintenance surface by design.

    Models that are not ``TenantScopedModel`` (``Tenant``, ``User``) use the
    default manager; they have no tenant filter to bypass.

Read-only models:
    ``AuditLogEntry`` is append-only (REQ-L1-011) and the admin is locked
    down to read-only via the three ``has_*_permission`` overrides.
"""
from __future__ import annotations

from django.contrib import admin
from django.contrib.auth import get_user_model

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
    AttributeVisibilityConfig,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# User — AUTH_USER_MODEL (already registered, kept here for completeness)
# ---------------------------------------------------------------------------


@admin.register(User)
class ReqFlowUserAdmin(admin.ModelAdmin):
    """Admin view for the ReqFlow User model.

    Uses a tailored ModelAdmin (not django.contrib.auth.admin.UserAdmin)
    because persistence.User has a different field set than AbstractUser
    (UUID pk, tenant FK, no groups/permissions tables, no last_login/
    date_joined).
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
class TenantAdmin(admin.ModelAdmin):
    """Admin view for the Tenant root identity (REQ-L1-008)."""

    list_display = ("name", "slug", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    ordering = ("name",)
    readonly_fields = ("created_at", "created_by", "modified_at", "modified_by", "version")


# ---------------------------------------------------------------------------
# Tenant-scoped entities — get_queryset uses unscoped() to bypass tenant filter
# ---------------------------------------------------------------------------


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    """Admin view for RBAC Role (REQ-L1-010)."""

    list_display = ("name", "tenant", "created_at")
    list_filter = ("tenant",)
    search_fields = ("name",)
    ordering = ("name",)
    readonly_fields = ("created_at", "created_by", "modified_at", "modified_by", "version")

    def get_queryset(self, request):
        # CRITICAL: bypass the tenant-isolating default manager.
        return Role.objects.unscoped()


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    """Admin view for Workspace (REQ-L1-008, REQ-L1-042)."""

    list_display = ("name", "tenant", "is_active", "closed_at", "created_at")
    list_filter = ("tenant", "is_active")
    search_fields = ("name",)
    ordering = ("name",)
    readonly_fields = ("created_at", "created_by", "modified_at", "modified_by", "version")

    def get_queryset(self, request):
        return Workspace.objects.unscoped()


@admin.register(Artifact)
class ArtifactAdmin(admin.ModelAdmin):
    """Admin view for Artifact (REQ-L1-001)."""

    list_display = ("id", "artifact_type", "workspace", "parent", "tenant", "created_at")
    list_filter = ("tenant", "artifact_type")
    search_fields = ("id", "artifact_type")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "created_by", "modified_at", "modified_by", "version")

    def get_queryset(self, request):
        return Artifact.objects.unscoped()


@admin.register(Requirement)
class RequirementAdmin(admin.ModelAdmin):
    """Admin view for Requirement (REQ-L1-001)."""

    list_display = ("title", "status", "category", "tenant", "created_at")
    list_filter = ("tenant", "status", "category")
    search_fields = ("title", "description")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "created_by", "modified_at", "modified_by", "version")

    def get_queryset(self, request):
        return Requirement.objects.unscoped()


@admin.register(StakeholderNeed)
class StakeholderNeedAdmin(admin.ModelAdmin):
    """Admin view for Stakeholder Need."""

    list_display = ("title", "status", "category", "tenant", "moscow_priority", "created_at")
    list_filter = ("tenant", "status", "category", "moscow_priority")
    search_fields = ("title", "description")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "created_by", "modified_at", "modified_by", "version")

    def get_queryset(self, request):
        return StakeholderNeed.objects.unscoped()


@admin.register(AttributeVisibilityConfig)
class AttributeVisibilityConfigAdmin(admin.ModelAdmin):
    """Admin view for Attribute Visibility Configs."""

    list_display = ("entity_type", "tenant", "created_at")
    list_filter = ("tenant", "entity_type")
    readonly_fields = ("id", "created_at", "created_by", "modified_at", "modified_by", "version")

    def get_queryset(self, request):
        return AttributeVisibilityConfig.objects.unscoped()


@admin.register(ArchitectureElement)
class ArchitectureElementAdmin(admin.ModelAdmin):
    """Admin view for ArchitectureElement (REQ-L1-002)."""

    list_display = ("title", "element_type", "tenant", "created_at")
    list_filter = ("tenant", "element_type")
    search_fields = ("title", "description")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "created_by", "modified_at", "modified_by", "version")

    def get_queryset(self, request):
        return ArchitectureElement.objects.unscoped()


@admin.register(TraceLink)
class TraceLinkAdmin(admin.ModelAdmin):
    """Admin view for TraceLink (REQ-L1-003)."""

    list_display = ("id", "link_type", "source", "target", "tenant", "created_at")
    list_filter = ("tenant", "link_type")
    search_fields = ("id", "link_type")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "created_by", "modified_at", "modified_by", "version")

    def get_queryset(self, request):
        return TraceLink.objects.unscoped()


@admin.register(TestCase)
class TestCaseAdmin(admin.ModelAdmin):
    """Admin view for TestCase (REQ-L1-012)."""

    list_display = ("title", "tenant", "created_at")
    list_filter = ("tenant",)
    search_fields = ("title", "description")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "created_by", "modified_at", "modified_by", "version")

    def get_queryset(self, request):
        return TestCase.objects.unscoped()


# ---------------------------------------------------------------------------
# AuditLogEntry — append-only, read-only in admin
# ---------------------------------------------------------------------------


@admin.register(AuditLogEntry)
class AuditLogEntryAdmin(admin.ModelAdmin):
    """Admin view for the append-only AuditLogEntry (REQ-L1-011).

    The model is append-only (REQ-L1-011, ADR-10) so all write/delete
    permissions are denied.  Read access remains so operators can audit
    history through the standard admin UI.
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

    def get_queryset(self, request):
        return AuditLogEntry.objects.unscoped()

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
class TestRunAdmin(admin.ModelAdmin):
    """Admin view for TestRun (REQ-L2-AS-030)."""

    list_display = ("name", "status", "workspace", "started_at", "finished_at", "tenant")
    list_filter = ("tenant", "status", "workspace")
    search_fields = ("name", "ci_job_id")
    ordering = ("-started_at",)
    readonly_fields = ("created_at", "created_by", "modified_at", "modified_by", "version")

    def get_queryset(self, request):
        return TestRun.objects.unscoped()


@admin.register(TestRunResult)
class TestRunResultAdmin(admin.ModelAdmin):
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

    def get_queryset(self, request):
        return TestRunResult.objects.unscoped()
