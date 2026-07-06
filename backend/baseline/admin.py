"""
Django admin registration for the baseline app (REQ-L2-BL-001/002/005/007).

Registers:

* :class:`BaselineSnapshot` — immutable baseline header (COMP-BL-003)
* :class:`BaselineDeltaIndexEntry` — append-only index entry

Tenant isolation:
    ``BaselineSnapshot`` inherits ``TenantScopedModel`` and uses the
    ``unscoped()`` manager in admin so all workspaces are visible.
    ``BaselineDeltaIndexEntry`` is a plain ``models.Model`` (no tenant FK); it
    uses the default manager.

Read-only models:
    ``BaselineDeltaIndexEntry`` is append-only (mirroring the immutability of
    the parent snapshot).  ``BaselineSnapshot`` is also immutable at the DB
    level (BEFORE UPDATE/DELETE triggers), but admins may still need to add
    or correct metadata in exceptional maintenance scenarios, so the snapshot
    registration remains writable and relies on the application-layer
    ``BaselineStore`` plus DB triggers to enforce immutability.
"""
from __future__ import annotations

from django.contrib import admin

from .models import BaselineDeltaIndexEntry, BaselineSnapshot


@admin.register(BaselineSnapshot)
class BaselineSnapshotAdmin(admin.ModelAdmin):
    """Admin view for the immutable baseline header (REQ-L2-BL-001/002/005)."""

    list_display = (
        "name",
        "scope",
        "workspace_id",
        "tenant",
        "created_by_ref",
        "created_at",
    )
    list_filter = ("scope", "workspace_id", "tenant")
    search_fields = ("name", "description", "created_by_ref")
    ordering = ("-created_at",)
    readonly_fields = (
        "created_at",
        "created_by",
        "modified_at",
        "modified_by",
        "version",
    )

    def get_queryset(self, request):
        # CRITICAL: bypass the tenant-isolating default manager.
        return BaselineSnapshot.unscoped.all()


@admin.register(BaselineDeltaIndexEntry)
class BaselineDeltaIndexEntryAdmin(admin.ModelAdmin):
    """Admin view for the append-only baseline delta index.

    Read-only: delta entries are immutable (mirroring the parent snapshot).
    The DB trigger in migration 0001_initial rejects UPDATE/DELETE; the admin
    is locked down to read-only for parity.
    """

    list_display = (
        "baseline",
        "item_id",
        "version",
        "entity_type",
    )
    list_filter = ("entity_type", "baseline")
    search_fields = ("item_id",)
    ordering = ("baseline", "item_id")
    readonly_fields = (
        "baseline",
        "item_id",
        "version",
        "entity_type",
    )

    def has_add_permission(self, request):
        return False  # read-only

    def has_change_permission(self, request, obj=None):
        return False  # read-only

    def has_delete_permission(self, request, obj=None):
        return False  # read-only
