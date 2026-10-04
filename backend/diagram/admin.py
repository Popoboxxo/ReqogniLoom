"""
Django admin registration for the diagram app (COMP-DS-001/002, REQ-L1-027).

Registers:

* :class:`Diagram` — the diagram record and its current payload

Datenmodell-Konsolidierung Task 28c-2 retired ``DiagramVersion`` (and with it
its read-only admin); content history now lives in
``persistence.ArtifactVersion`` alongside every other artifact type's.

Tenant isolation (SEC-04, ADR-011):
    ``Diagram`` inherits ``TenantScopedModel`` and ``TenantScopedAdminMixin``,
    so the admin is narrowed to the requesting staff user's tenant.
"""
from __future__ import annotations

from django.contrib import admin

from persistence.tenant_admin import TenantScopedAdminMixin

from .models import Diagram


@admin.register(Diagram)
class DiagramAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
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
