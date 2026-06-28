"""
Django admin registration for the diagram app (COMP-DS-001/002, REQ-L1-027).

Registers:

* :class:`Diagram` — mutable header record
* :class:`DiagramVersion` — append-only immutable payload snapshot

Read-only:
    ``DiagramVersion`` is immutable (REQ-L2-DS-001, REQ-L3-DM-002); the admin
    is locked down to read-only to match.

Tenant isolation:
    Both models inherit ``TenantScopedModel``. ``get_queryset`` uses the
    ``unscoped()`` manager to bypass the tenant filter.
"""
from __future__ import annotations

from django.contrib import admin

from .models import Diagram, DiagramVersion


@admin.register(Diagram)
class DiagramAdmin(admin.ModelAdmin):
    """Admin view for the Diagram header (REQ-L2-DS-001)."""

    list_display = (
        "name",
        "diagram_type",
        "tenant",
        "current_version",
        "created_at",
    )
    list_filter = ("tenant", "diagram_type")
    search_fields = ("name", "description")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "created_by", "modified_at", "modified_by", "version")

    def get_queryset(self, request):
        # CRITICAL: bypass the tenant-isolating default manager.
        return Diagram.objects.unscoped()


@admin.register(DiagramVersion)
class DiagramVersionAdmin(admin.ModelAdmin):
    """Admin view for the immutable DiagramVersion (REQ-L3-DM-002).

    Read-only: each DiagramVersion is a frozen snapshot; updates create a new
    version rather than mutating an existing one.
    """

    list_display = (
        "diagram",
        "version_number",
        "payload_format",
        "tenant",
        "created_at",
    )
    list_filter = ("tenant", "payload_format", "diagram")
    search_fields = ("diagram__name", "payload")
    ordering = ("diagram", "-version_number")
    readonly_fields = (
        "diagram",
        "version_number",
        "payload_format",
        "payload",
        "created_at",
        "created_by",
        "modified_at",
        "modified_by",
        "version",
        "tenant",
    )

    def get_queryset(self, request):
        return DiagramVersion.objects.unscoped()

    def has_add_permission(self, request):
        return False  # read-only

    def has_change_permission(self, request, obj=None):
        return False  # read-only

    def has_delete_permission(self, request, obj=None):
        return False  # read-only
