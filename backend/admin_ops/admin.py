"""
Django admin registration for the admin_ops app (REQ-L1-046).

Registers the disaster-recovery bookkeeping entity:

* :class:`BackupMetadata` — instance-level record of a system backup

Read-only:
    The admin surfaces existing backup rows for inspection. Backup
    creation and restoration are driven by the admin_ops services (not by
    hand-editing rows), so the admin is locked down to read-only.

Tenant isolation:
    ``BackupMetadata`` is NOT a ``TenantScopedModel`` — backups are
    system-level artefacts that may legitimately span tenants (see
    admin_ops.models). The default manager is correct: there is no
    tenant filter to bypass.
"""
from __future__ import annotations

from django.contrib import admin

from .models import BackupMetadata


@admin.register(BackupMetadata)
class BackupMetadataAdmin(admin.ModelAdmin):
    """Admin view for system backup records (REQ-L1-046).

    Read-only: backups are produced and restored by the admin_ops services;
    operators should never hand-edit metadata rows. The admin surfaces
    existing backups for status inspection and audit purposes.
    """

    list_display = (
        "id",
        "status",
        "backup_type",
        "file_size_bytes",
        "completed_at",
        "created_at",
    )
    list_filter = ("status", "backup_type")
    search_fields = ("id", "file_path", "checksum_sha256", "error_message")
    ordering = ("-created_at",)
    readonly_fields = (
        "status",
        "backup_type",
        "file_path",
        "file_size_bytes",
        "checksum_sha256",
        "error_message",
        "completed_at",
        "metadata",
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
