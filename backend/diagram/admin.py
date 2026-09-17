"""
Django admin registration for the diagram app (COMP-DS-001/002, REQ-L1-027).

Registers:

* :class:`Diagram` — the diagram record and its current payload

Datenmodell-Konsolidierung Task 28c-2 retired ``DiagramVersion`` (and with it
its read-only admin); content history now lives in
``persistence.ArtifactVersion`` alongside every other artifact type's.

Tenant isolation:
    ``Diagram`` inherits ``TenantScopedModel``. ``get_queryset`` uses the
    ``unscoped()`` manager to bypass the tenant filter.
"""
from __future__ import annotations

from django.contrib import admin

from .models import Diagram


@admin.register(Diagram)
class DiagramAdmin(admin.ModelAdmin):
    """Admin view for the Diagram record (REQ-L2-DS-001)."""

    list_display = (
        "name",
        "diagram_type",
        "tenant",
        "current_revision",
        "created_at",
    )
    list_filter = ("tenant", "diagram_type")
    search_fields = ("name", "description")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "created_by", "modified_at", "modified_by", "version")

    def get_queryset(self, request):
        # CRITICAL: bypass the tenant-isolating default manager.
        return Diagram.unscoped.all()
