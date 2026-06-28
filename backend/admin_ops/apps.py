"""App configuration for the admin_ops (Disaster Recovery) Django app."""
from django.apps import AppConfig


class AdminOpsConfig(AppConfig):
    """AdminOps — system-wide Disaster Recovery foundation (REQ-L1-046).

    Responsibilities:
    - Persists ``BackupMetadata`` (instance-level) for system-wide backups.
    - Exposes ``BackupService`` (admin-only) for create / list / get / delete.
    - Exposes ``AdminRestoreService`` (admin-only, captcha-gated) for restore.

    No REST or MCP surface in this wave — see
    ``backend/admin_ops/services/INTERFACES.md`` §9 (Out of scope) for the
    deferred items.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "admin_ops"
    verbose_name = "AdminOps — Disaster Recovery"
