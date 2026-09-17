"""
admin_ops — BackupService (REQ-L1-046).

Stateless service that owns the lifecycle of a :class:`BackupMetadata`
row from creation through deletion. All public methods are admin-only
and produce a corresponding AuditLog entry via ``ServiceBase._audit``.

The actual data extraction is delegated to ``django.core.management``.
This keeps the file format deterministic (``dumpdata`` -> JSON) and
reversible (``loaddata`` from :class:`AdminRestoreService`).
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from django.core.management import call_command
from django.db import transaction

from application.base import ServiceBase
from auth_tenancy.context import AuthContext

from admin_ops.models import BackupMetadata, BackupStatus, BackupType
from admin_ops.services.exceptions import BackupNotFoundError, BackupStorageError
from admin_ops.services.paths import absolute_backup_path, backup_root

logger = logging.getLogger(__name__)


# Maximum number of backups returned by list_backups() in one call. Hard cap
# to prevent an operator from pulling a multi-thousand-row page by accident.
_LIST_LIMIT_CAP = 1000


class BackupService:
    """Admin-only service that creates / lists / gets / deletes backups.

    Stateless. The service holds no per-request state; the only persistent
    artefact is the :class:`BackupMetadata` row.

    Public API (see ``backend/admin_ops/services/INTERFACES.md`` §2.1):

    * :meth:`create_backup` — create a row + write the data file.
    * :meth:`list_backups` — admin overview listing.
    * :meth:`get_backup`   — single row lookup.
    * :meth:`delete_backup`— remove the row (and the file on disk).
    """

    # -- Write: create ---------------------------------------------------

    def create_backup(
        self,
        ctx: AuthContext,
        *,
        backup_type: str = BackupType.FULL,
        metadata: Optional[dict] = None,
    ) -> BackupMetadata:
        """Create a new backup and persist its row (admin-only).

        The method runs the full ``create_backup`` workflow inside a
        single :func:`django.db.transaction.atomic` block:

        1. Gate the caller (admin role).
        2. Validate the ``backup_type`` argument.
        3. Insert a ``pending`` row.
        4. Run ``dumpdata`` to a buffer; compute SHA-256 and size.
        5. Write the file to ``MEDIA_ROOT/backups/<id>.json``.
        6. Update the row to ``completed`` with checksum + size.
        7. Emit the ``backup.create`` audit entry.

        Any failure inside steps 4-6 rolls back the row. A *second*
        small atomic block then marks the row as ``failed`` with the
        captured exception so the operator can see what happened; if
        that block also fails, the original exception is re-raised and
        the row is left ``pending`` (best-effort failure accounting).
        """
        ServiceBase._assert_permission(ctx, "admin")
        ServiceBase._set_tenant_context(ctx)

        if backup_type not in BackupType.values:
            raise ValueError(
                f"Unknown backup_type {backup_type!r}; expected one of "
                f"{list(BackupType.values)}."
            )

        summary_metadata = dict(metadata or {})
        backup_id = uuid.uuid4()
        target_path = os.path.join(
            backup_root(), f"{backup_id}.json"
        )

        try:
            with transaction.atomic():
                row = BackupMetadata.objects.create(
                    id=backup_id,
                    status=BackupStatus.PENDING,
                    backup_type=backup_type,
                    metadata=summary_metadata,
                    created_by_id=ctx.user_id,
                )

                # 4. Run dumpdata into an in-memory buffer so we can
                # compute checksum + size in the same transaction.
                buf = io.StringIO()
                call_command("dumpdata", stdout=buf, format="json")
                payload = buf.getvalue().encode("utf-8")
                digest = hashlib.sha256(payload).hexdigest()
                size = len(payload)

                # 5. Write the file. We do this inside the same
                # transaction so a write failure rolls back the row.
                os.makedirs(backup_root(), exist_ok=True)
                with open(target_path, "wb") as fh:
                    fh.write(payload)

                # 6. Flip the row to completed.
                row.status = BackupStatus.COMPLETED
                row.file_path = os.path.relpath(target_path, backup_root())
                row.file_size_bytes = size
                row.checksum_sha256 = digest
                row.completed_at = datetime.now(timezone.utc)
                row.modified_by_id = ctx.user_id
                # Stamp the summary metadata (counts only — we don't
                # double-store the data file's contents).
                summary_metadata.setdefault("file_size_bytes", size)
                summary_metadata.setdefault("checksum_sha256", digest)
                row.metadata = summary_metadata
                row.save()

                # 7. Audit. The v1 audit writer ignores ``details``;
                # encode the operation_kind in ``change_reason`` so
                # operators can still grep the audit log for it.
                ServiceBase._audit(
                    ctx,
                    operation="create",
                    entity_type="BackupMetadata",
                    entity_id=row.id,
                    change_reason=(
                        f"backup.create backup_type={backup_type} "
                        f"file_size_bytes={size}"
                    ),
                    details={
                        "operation_kind": "backup.create",
                        "backup_type": backup_type,
                        "file_path": row.file_path,
                        "file_size_bytes": size,
                        "checksum_sha256": digest,
                    },
                )

                logger.info(
                    "BackupService: created backup id=%s size=%d",
                    row.id,
                    size,
                )
                return row
        except OSError as exc:
            # GitHub #37: a filesystem error (typically PermissionError when
            # the backup directory is not writable) must not leak the raw OS
            # message ("Permission denied: /app/backups/") to REST/MCP
            # callers. Record the real cause for operators, but raise a
            # clean, actionable error for the caller.
            self._record_failure(
                backup_id=backup_id,
                error=str(exc),
                backup_type=backup_type,
            )
            logger.error(
                "BackupService: backup directory %r is not writable: %s",
                backup_root(),
                exc,
            )
            raise BackupStorageError(
                "Backup storage is not writable. Configure the BACKUP_DIR "
                "environment variable to point at a writable directory, or "
                "check the permissions of the default backup path."
            ) from exc
        except Exception as exc:
            self._record_failure(
                backup_id=backup_id,
                error=str(exc),
                backup_type=backup_type,
            )
            raise

    # -- Read: list / get -------------------------------------------------

    def list_backups(
        self,
        ctx: AuthContext,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[BackupMetadata]:
        """Return backups ordered by ``-created_at`` (admin-only).

        The ``limit`` is capped to :data:`_LIST_LIMIT_CAP` rows; negative
        or non-integer inputs are coerced to safe defaults.
        """
        ServiceBase._assert_permission(ctx, "admin")
        ServiceBase._set_tenant_context(ctx)

        safe_limit = max(1, min(int(limit or 100), _LIST_LIMIT_CAP))
        safe_offset = max(0, int(offset or 0))

        # The table is instance-level; the ``objects`` manager is the
        # plain Django manager (no tenant filter). We use it directly.
        return list(
            BackupMetadata.objects.all()
            .order_by("-created_at")[safe_offset : safe_offset + safe_limit]
        )

    def get_backup(
        self, ctx: AuthContext, backup_id: UUID
    ) -> BackupMetadata:
        """Return a single backup row (admin-only).

        Raises :class:`BackupNotFoundError` if the row does not exist.
        """
        ServiceBase._assert_permission(ctx, "admin")
        ServiceBase._set_tenant_context(ctx)

        try:
            return BackupMetadata.objects.get(pk=backup_id)
        except BackupMetadata.DoesNotExist as exc:
            raise BackupNotFoundError(
                f"Backup {backup_id} not found."
            ) from exc

    # -- Write: delete ---------------------------------------------------

    def delete_backup(
        self, ctx: AuthContext, backup_id: UUID
    ) -> bool:
        """Delete a backup row and the file on disk (admin-only).

        Returns ``True`` if a row was removed, ``False`` if the id did
        not match anything. The audit row is only written on a real
        delete (idempotent no-op returns ``False`` without audit noise).
        """
        ServiceBase._assert_permission(ctx, "admin")
        ServiceBase._set_tenant_context(ctx)

        with transaction.atomic():
            row = (
                BackupMetadata.objects.filter(pk=backup_id).first()
            )
            if row is None:
                return False

            # Capture fields for the audit row before delete clears them.
            row_id = row.id
            row_path = row.file_path
            row_type = row.backup_type

            # Best-effort file removal — never let I/O block the DB delete.
            if row_path:
                abs_path = absolute_backup_path(row_path)
                try:
                    if os.path.isfile(abs_path):
                        os.remove(abs_path)
                except OSError as exc:
                    logger.warning(
                        "BackupService: could not remove file %s for "
                        "backup %s: %s",
                        abs_path,
                        row_id,
                        exc,
                    )

            row.delete()

            ServiceBase._audit(
                ctx,
                operation="delete",
                entity_type="BackupMetadata",
                entity_id=row_id,
                change_reason=f"backup.delete backup_type={row_type}",
                details={
                    "operation_kind": "backup.delete",
                    "backup_type": row_type,
                },
            )

            logger.info(
                "BackupService: deleted backup id=%s type=%s",
                row_id,
                row_type,
            )
            return True

    # -- Helpers ----------------------------------------------------------

    @staticmethod
    def _record_failure(
        *,
        backup_id: UUID,
        error: str,
        backup_type: str,
    ) -> None:
        """Best-effort: mark the failed row as ``status='failed'``.

        Runs in a separate atomic block so a rollback in the main flow
        has already cleared the row — we re-insert a ``failed`` marker
        keyed on the same id. Used by :meth:`create_backup` when the
        dumpdata / file write phase blows up.
        """
        try:
            with transaction.atomic():
                BackupMetadata.objects.create(
                    id=backup_id,
                    status=BackupStatus.FAILED,
                    backup_type=backup_type,
                    error_message=error[:8000],
                    completed_at=datetime.now(timezone.utc),
                )
        except Exception:  # pragma: no cover - best-effort path
            logger.exception(
                "BackupService: failed to record failure for backup %s",
                backup_id,
            )


__all__ = ["BackupService"]
