"""
Django admin registration for the presets app (COMP-PC-001/002/003).

Registers the single persistent entity that backs the preset / terminology
profile / downgrade policy configuration:

* :class:`WorkspacePresetConfig` — per-workspace preset tier + terminology
  profile (REQ-L2-PC-001/002/008, REQ-L3-PC002-003, REQ-L3-PC003-003)

Tenant isolation:
    ``WorkspacePresetConfig`` inherits ``TenantScopedModel`` and uses the
    ``unscoped()`` manager in admin.
"""
from __future__ import annotations

from django.contrib import admin

from .models import WorkspacePresetConfig


@admin.register(WorkspacePresetConfig)
class WorkspacePresetConfigAdmin(admin.ModelAdmin):
    """Admin view for the per-workspace preset configuration."""

    list_display = (
        "workspace",
        "active_tier",
        "terminology_profile",
        "downgrade_policy",
        "tenant",
    )
    list_filter = ("active_tier", "terminology_profile", "downgrade_policy", "tenant")
    search_fields = ("workspace__name",)
    ordering = ("tenant", "workspace")
    readonly_fields = ("created_at", "created_by", "modified_at", "modified_by", "version")

    def get_queryset(self, request):
        # CRITICAL: bypass the tenant-isolating default manager.
        return WorkspacePresetConfig.objects.unscoped()
