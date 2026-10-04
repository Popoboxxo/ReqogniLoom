"""
Django admin registration for the audit app (COMP-AL-001/002, REQ-L2-AL-001).

Registers the single append-only audit log entity:

* :class:`AuditEntry` — append-only operational audit log

Read-only:
    The model is append-only (REQ-L2-AL-003, ADR-AL-03): both DB triggers
    and the model ``save``/``delete`` overrides reject UPDATE/DELETE.  The
    admin is locked down to read-only to match.

Tenant isolation (SEC-04, ADR-011):
    ``AuditEntry`` inherits ``TenantScopedModel`` and ``TenantScopedAdminMixin``,
    so ``get_queryset`` and the per-object permission checks are narrowed to the
    requesting staff user's tenant. Read-only is preserved (the mixin's checks
    AND the model's append-only guards).
"""
from __future__ import annotations

from django.contrib import admin

from persistence.tenant_admin import TenantScopedAdminMixin

from .models import AuditEntry


@admin.register(AuditEntry)
class AuditEntryAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
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

    def has_add_permission(self, request):
        return False  # read-only

    def has_change_permission(self, request, obj=None):
        return False  # read-only

    def has_delete_permission(self, request, obj=None):
        return False  # read-only
