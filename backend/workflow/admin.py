"""
Django admin registration for the workflow app (COMP-WE-001/003, REQ-L2-WE).

Registers the engine-level entities that extend the thin persistence-layer
placeholders:

* :class:`WorkflowEngineDefinition` — per-workspace state-machine config
* :class:`WorkflowItemState` — current state of a tracked item
* :class:`WorkflowHistoryEntry` — append-only transition history

Read-only:
    ``WorkflowHistoryEntry`` is append-only (REQ-L2-WE-003, ADR-L3-WE003-03);
    the admin is locked down to read-only to match.

Tenant isolation (SEC-04, ADR-011):
    All three inherit ``TenantScopedModel`` and ``TenantScopedAdminMixin``, so
    ``get_queryset`` and the per-object permission checks are narrowed to the
    requesting staff user's tenant. A staff user of tenant A can neither list
    nor change tenant B's workflow rows.
"""
from __future__ import annotations

from django.contrib import admin

from persistence.tenant_admin import TenantScopedAdminMixin

from .models import WorkflowEngineDefinition, WorkflowHistoryEntry, WorkflowItemState


@admin.register(WorkflowEngineDefinition)
class WorkflowEngineDefinitionAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin view for the workflow definition (REQ-L2-WE-002, REQ-L3-WE001-001)."""

    list_display = (
        "item_type",
        "preset",
        "is_custom",
        "workspace_id",
        "tenant",
        "created_at",
    )
    list_filter = ("tenant", "preset", "is_custom", "workspace_id")
    search_fields = ("item_type",)
    ordering = ("tenant", "workspace_id", "item_type")
    readonly_fields = ("created_at", "created_by", "modified_at", "modified_by", "version")


@admin.register(WorkflowItemState)
class WorkflowItemStateAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin view for the per-item workflow state (REQ-L3-WE003-001/002)."""

    list_display = (
        "item_type",
        "item_id",
        "current_state",
        "workspace_id",
        "tenant",
        "definition",
    )
    list_filter = ("tenant", "item_type", "current_state", "workspace_id")
    search_fields = ("item_id", "current_state", "item_type")
    ordering = ("tenant", "workspace_id", "item_type")
    readonly_fields = ("created_at", "created_by", "modified_at", "modified_by", "version")


@admin.register(WorkflowHistoryEntry)
class WorkflowHistoryEntryAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin view for the append-only workflow history (REQ-L2-WE-003).

    Read-only: history entries are immutable (ADR-L3-WE003-03). The
    application-level ``save`` override rejects UPDATE; the admin is locked
    down to read-only to match.
    """

    list_display = (
        "item_state",
        "from_state",
        "to_state",
        "transitioned_by",
        "transitioned_at",
        "workspace_id",
        "tenant",
    )
    list_filter = ("tenant", "workspace_id", "from_state", "to_state")
    search_fields = (
        "transitioned_by",
        "from_state",
        "to_state",
        "change_reason",
        "signature_seal",
    )
    ordering = ("-transitioned_at",)
    readonly_fields = (
        "item_state",
        "from_state",
        "to_state",
        "transitioned_by",
        "transitioned_at",
        "change_reason",
        "signature_seal",
        "workspace_id",
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
