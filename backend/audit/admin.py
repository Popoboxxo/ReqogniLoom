"""
Django admin registration for the audit app (COMP-AL-001/002, REQ-L2-AL-001).

Registers the single append-only audit log entity:

* :class:`AuditEntry` — append-only operational audit log

Read-only:
    The model is append-only (REQ-L2-AL-003, ADR-AL-03): both DB triggers
    and the model ``save``/``delete`` overrides reject UPDATE/DELETE.  The
    admin is locked down to read-only to match.

Tenant isolation:
    ``AuditEntry`` inherits ``TenantScopedModel``. ``get_queryset`` uses the
    ``unscoped()`` manager (whose ``AppendOnlyUnscopedManager`` subclass
    blocks UPDATE/DELETE just like the default manager).
"""
from __future__ import annotations

from django.contrib import admin

from .models import AuditEntry


@admin.register(AuditEntry)
class AuditEntryAdmin(admin.ModelAdmin):
    """Admin view for the append-only audit log (REQ-L2-AL-001/002/003)."""

    list_display = (
        "timestamp",
        "source",
        "actor",
        "actor_type",
        "op",
        "entity_type",
        "entity_id",
        "tenant",
    )
    list_filter = ("source", "actor_type", "op", "entity_type", "tenant")
    search_fields = ("actor", "entity_id", "entity_type", "client_name", "api_key_hash")
    ordering = ("-timestamp",)
    readonly_fields = (
        "actor",
        "actor_type",
        "op",
        "entity_type",
        "entity_id",
        "entity_version",
        "change_reason",
        "timestamp",
        "source",
        "client_name",
        "api_key_hash",
        "tenant",
        "created_at",
        "created_by",
        "modified_at",
        "modified_by",
        "version",
    )

    def get_queryset(self, request):
        # CRITICAL: bypass the tenant-isolating default manager.
        return AuditEntry.objects.unscoped()

    def has_add_permission(self, request):
        return False  # read-only

    def has_change_permission(self, request, obj=None):
        return False  # read-only

    def has_delete_permission(self, request, obj=None):
        return False  # read-only
