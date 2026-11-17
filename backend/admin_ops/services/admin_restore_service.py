"""
admin_ops — AdminRestoreService (REQ-L1-046).

The most dangerous operation in the system. To prevent accidental or
malicious invocation :meth:`AdminRestoreService.restore` requires a
typed confirmation text (``RESTORE``) and the ``admin`` role. The body
runs inside a single ``transaction.atomic()`` block — any failure
rolls back the entire restore.

RESTORE SEMANTICS — NON-DESTRUCTIVE OVERLAY (EXT-004)
-----------------------------------------------------
A restore is *not* a destructive rollback. The service does NOT truncate
tables, drop/recreate the schema, or delete rows created after the backup.
``loaddata`` replays the dumpdata payload by primary key: rows that exist
both in the backup and in the live DB are patched back to their snapshot
values (upsert), while rows created after the backup are left untouched and
remain visible. This is deliberate: under tenant Row-Level Security and the
append-only audit triggers, a truncate/drop "true rollback" would destroy
live data and audit history that the backup cannot reconstruct.

Consequently ``RestoreResult.restored_tables`` / ``rows_per_table`` describe
the *contents of the fixture file* (what the overlay will write), not a count
of tables or rows that were deleted/replaced. They are derived from the
serialized payload itself, so they are honest even when a row was already in
sync and no visible change occurred.

See ``backend/admin_ops/services/INTERFACES.md`` §4 for the full
restore-safety contract and §5 for the audit log mapping.
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from django.core.management import call_command
from django.db import transaction

from admin_ops.models import BackupMetadata
from admin_ops.services.exceptions import BackupNotFoundError
from admin_ops.services.paths import absolute_backup_path
from application.base import ServiceBase, ValidationError
from auth_tenancy.context import AuthContext

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
        restored_tables: Sorted ``app_label.model`` labels present in the
            backup's serialized payload — the tables the overlay will write.
            Empty when the fixture could not be summarized (the restore
            itself still succeeds; the summary is informational only).
        rows_per_table: ``{app_label.model: count}`` derived from the same
            payload — how many serialized rows exist per model.
    """

    backup_id: UUID
    started_at: datetime
    completed_at: datetime
    restored_tables: list[str] = field(default_factory=list)
    rows_per_table: dict[str, int] = field(default_factory=dict)


def _summarize_fixture(abs_path: str) -> tuple[list[str], dict[str, int]]:
    """Return ``(sorted model labels, per-model counts)`` for a dumpdata file.

    The backup format is ``dumpdata --format=json``, optionally gzip-compressed
    (``BackupService.create_backup`` since issue #823). Each top-level object
    carries a ``model`` key of the form ``app_label.modelname``; counting those
    keys gives an honest per-table row count for the overlay that ``loaddata``
    is about to apply.

    Best-effort by contract: an unreadable, malformed or non-dumpdata file
    yields an empty summary plus a warning rather than failing the restore —
    these fields are diagnostic metadata, not a precondition for loading.

    Args:
        abs_path: Absolute path of the on-disk fixture.

    Returns:
        Tuple of (sorted distinct model labels, {model label: row count}).
    """
    try:
        with open(abs_path, "rb") as fh:
            raw = fh.read()
        # gzip magic bytes — BackupService writes `<id>.json.gz` since #823.
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        payload = json.loads(raw.decode("utf-8"))
        counts: Counter[str] = Counter(
            obj["model"]
            for obj in payload
            if isinstance(obj, dict) and obj.get("model")
        )
        return sorted(counts), dict(counts)
    except Exception:  # noqa: BLE001 — diagnostic only, never block a restore
        logger.warning(
            "AdminRestoreService: could not summarize fixture %s",
            abs_path,
            exc_info=True,
        )
        return [], {}


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
        started_at = datetime.now(UTC)

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

                # 7. Summarize the serialized payload BEFORE loading it,
                #    then run loaddata. The file was produced by ``dumpdata``
                #    (see BackupService.create_backup), possibly gzipped, so
                #    the format is guaranteed to be compatible. The summary
                #    is honest about the file's contents and is informational
                #    only — a failure to summarize never blocks the restore.
                restored_tables, rows_per_table = _summarize_fixture(abs_path)
                call_command("loaddata", abs_path, verbosity=0)

                completed_at = datetime.now(UTC)
                result = RestoreResult(
                    backup_id=backup_id,
                    started_at=started_at,
                    completed_at=completed_at,
                    restored_tables=restored_tables,
                    rows_per_table=rows_per_table,
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


__all__ = ["RESTORE_CAPTCHA", "AdminRestoreService", "RestoreResult"]
