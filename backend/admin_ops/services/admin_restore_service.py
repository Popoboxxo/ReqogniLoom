"""
admin_ops — AdminRestoreService (REQ-L1-046).

The most dangerous operation in the system. To prevent accidental or
malicious invocation :meth:`AdminRestoreService.restore` requires a
typed confirmation text (``RESTORE``) and the ``admin`` role. The body
runs inside a single ``transaction.atomic()`` block — any failure
rolls back the entire restore.

See ``backend/admin_ops/services/INTERFACES.md`` §4 for the full
restore-safety contract and §5 for the audit log mapping.
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from django.core.management import call_command
from django.db import transaction

from application.base import ServiceBase, ValidationError
from auth_tenancy.context import AuthContext

from admin_ops.models import BackupMetadata
from admin_ops.services.exceptions import BackupNotFoundError
from admin_ops.services.paths import absolute_backup_path

logger = logging.getLogger(__name__)


# The literal confirmation text the caller must type. Comparison is
# exact and case-sensitive — see INTERFACES.md §2.2.1.
RESTORE_CAPTCHA = "RESTORE"


@dataclass(frozen=True)
class RestoreResult:
    """Outcome of a successful :meth:`AdminRestoreService.restore` call.

    Attributes:
        backup_id: The :class:`BackupMetadata` id that was restored.
        started_at: Wall-clock time the restore body began executing.
        completed_at: Wall-clock time the restore body returned.
        restored_tables: ``app_label.ModelName`` strings for each model
            touched by the ``loaddata`` step (best-effort; populated
            when the dumpdata payload advertises a per-app summary).
        rows_per_table: ``{table: count}``; same caveat as above.
    """

    backup_id: UUID
    started_at: datetime
    completed_at: datetime
    restored_tables: list[str] = field(default_factory=list)
    rows_per_table: dict[str, int] = field(default_factory=dict)


class AdminRestoreService:
    """Admin-only service that restores a :class:`BackupMetadata` (REQ-L1-046).

    Stateless. The single public method is :meth:`restore`; the
    captcha, admin-gate and restorable-state checks happen in that
    order before any DB read so a malformed call leaves no trace.
    """

    def restore(
        self,
        ctx: AuthContext,
        *,
        backup_id: UUID,
        confirmation_text: str,
    ) -> RestoreResult:
        """Restore the database from the named backup (admin-only).

        Args:
            ctx: Caller's auth context; must have the ``admin`` role.
            backup_id: UUID of the :class:`BackupMetadata` to restore.
            confirmation_text: Must be the exact string ``"RESTORE"`` —
                any other value (including the lowercase form, a
                trailing space, or extra punctuation) raises
                :class:`ValidationError` with the constant message
                ``"Captcha mismatch"`` *before* any DB read.

        Returns:
            A :class:`RestoreResult` describing what was restored.

        Raises:
            PermissionDeniedError: Caller lacks the ``admin`` role.
            ValidationError: ``confirmation_text`` is not the literal
                ``"RESTORE"`` (case-sensitive).
            BackupNotFoundError: The backup id does not exist or the
                row is not in a restorable state (status != completed).
        """
        # 1. Admin gate.
        ServiceBase._assert_permission(ctx, "admin")

        # 2. Captcha gate — exact, case-sensitive, before any DB read.
        if confirmation_text != RESTORE_CAPTCHA:
            raise ValidationError("Captcha mismatch")

        # 3. Tenant context (so the audit log can resolve the admin's tenant).
        ServiceBase._set_tenant_context(ctx)

        # 4. Backup state gate — the row must exist and be 'completed'.
        try:
            backup = BackupMetadata.objects.get(pk=backup_id)
        except BackupMetadata.DoesNotExist as exc:
            raise BackupNotFoundError(
                f"Backup {backup_id} not found."
            ) from exc
        if not backup.is_restorable:
            raise BackupNotFoundError(
                f"Backup {backup_id} is not restorable "
                f"(status={backup.status})."
            )

        # Snapshot for the audit entry before the body starts.
        snapshot_path = backup.file_path
        restore_event_id = uuid.uuid4()
        started_at = datetime.now(timezone.utc)

        try:
            with transaction.atomic():
                # 5. Audit 'start' inside the same transaction. The v1
                # audit writer ignores ``details``; encode the
                # operation_kind in ``change_reason`` so the audit log
                # is greppable.
                ServiceBase._audit(
                    ctx,
                    operation="create",
                    entity_type="BackupRestore",
                    entity_id=restore_event_id,
                    change_reason=f"restore.start backup_id={backup_id}",
                    details={
                        "operation_kind": "restore.start",
                        "backup_id": str(backup_id),
                        "backup_type": backup.backup_type,
                    },
                )

                # 6. Resolve the absolute file path and confirm it
                #    still exists on disk. We deliberately fail
                #    *inside* the atomic block so the audit row
                #    rolls back too — the operator can re-run
                #    with a known-good backup.
                if not snapshot_path:
                    raise BackupNotFoundError(
                        f"Backup {backup_id} has no file_path; "
                        "the data file is missing."
                    )
                abs_path = absolute_backup_path(snapshot_path)
                if not os.path.isfile(abs_path):
                    raise FileNotFoundError(
                        f"Backup file {abs_path} is missing on disk."
                    )

                # 7. Run loaddata. The data file was produced by
                #    ``dumpdata`` (see BackupService.create_backup),
                #    so the format is guaranteed to be compatible.
                call_command("loaddata", abs_path, verbosity=0)

                completed_at = datetime.now(timezone.utc)
                result = RestoreResult(
                    backup_id=backup_id,
                    started_at=started_at,
                    completed_at=completed_at,
                )

                # 8. Audit 'complete' inside the same transaction.
                ServiceBase._audit(
                    ctx,
                    operation="update",
                    entity_type="BackupRestore",
                    entity_id=restore_event_id,
                    change_reason=(
                        f"restore.complete backup_id={backup_id}"
                    ),
                    details={
                        "operation_kind": "restore.complete",
                        "backup_id": str(backup_id),
                        "duration_seconds": (
                            completed_at - started_at
                        ).total_seconds(),
                    },
                )

                logger.info(
                    "AdminRestoreService: restore complete backup_id=%s",
                    backup_id,
                )
                return result
        except Exception as exc:
            self._record_failure(
                ctx=ctx,
                restore_event_id=restore_event_id,
                backup_id=backup_id,
                error=str(exc),
            )
            raise

    # -- Helpers ----------------------------------------------------------

    @staticmethod
    def _record_failure(
        *,
        ctx: AuthContext,
        restore_event_id: UUID,
        backup_id: UUID,
        error: str,
    ) -> None:
        """Best-effort: write a ``restore.fail`` audit row.

        Runs in a separate atomic block because the main transaction
        has already rolled back. If this also fails, the operator
        sees the failure in the application log only.
        """
        try:
            with transaction.atomic():
                ServiceBase._audit(
                    ctx,
                    operation="update",
                    entity_type="BackupRestore",
                    entity_id=restore_event_id,
                    change_reason=(
                        f"restore.fail backup_id={backup_id} "
                        f"error={error[:500]}"
                    ),
                    details={
                        "operation_kind": "restore.fail",
                        "backup_id": str(backup_id),
                        "error": error[:1000],
                    },
                )
        except Exception:  # pragma: no cover - best-effort path
            logger.exception(
                "AdminRestoreService: failed to record restore.fail "
                "for backup %s",
                backup_id,
            )


__all__ = ["AdminRestoreService", "RestoreResult", "RESTORE_CAPTCHA"]
