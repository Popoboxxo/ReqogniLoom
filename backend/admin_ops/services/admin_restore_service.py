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

P7 — CHECKED TARGET-INSTANCE RESTORE (D17)
------------------------------------------
The overlay above is now *checked* and *targeted*:

* the on-disk bytes are SHA-256 verified against ``BackupMetadata.checksum_sha256``
  **before** ``loaddata`` runs (a corrupt/truncated file can no longer be partially
  applied);
* ``metadata["format_version"]`` is validated against
  :data:`SUPPORTED_FORMAT_VERSIONS` (legacy rows without the key default to
  :data:`DEFAULT_BACKUP_FORMAT_VERSION`);
* ``dry_run=True`` executes the checksum + summary + target validation and
  returns an exact plan, but never calls ``loaddata`` and writes no audit row;
* ``target_tenant`` / ``target_workspace`` make the destination explicit. The
  RLS session context is armed for ``target_tenant`` around the load and always
  restored in a ``finally``. A wrong destination is a validation error, not a
  silent no-op.

The Sidecar stays the DR source of truth (ADR-012); this path is the checked
application-level restore for a *target instance*, never a second DR truth.
"""
from __future__ import annotations

import gzip
import hashlib
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
from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext

logger = logging.getLogger(__name__)


# The literal confirmation text the caller must type. Comparison is
# exact and case-sensitive — see INTERFACES.md §2.2.1.
RESTORE_CAPTCHA = "RESTORE"

# P7 / D17: versioned on-disk backup format. Stamped by BackupService on create;
# older rows without the key are treated as the first version.
DEFAULT_BACKUP_FORMAT_VERSION = "1"
SUPPORTED_FORMAT_VERSIONS = frozenset({DEFAULT_BACKUP_FORMAT_VERSION})


class BackupChecksumMismatch(ValidationError):
    """The backup file's SHA-256 differs from ``BackupMetadata.checksum_sha256``.

    Subclasses ``ValidationError`` so the existing REST (400) and MCP
    (``VALIDATION_ERROR``) adapters translate it without changes.
    """


class UnsupportedBackupFormat(ValidationError):
    """The backup's ``format_version`` is not in :data:`SUPPORTED_FORMAT_VERSIONS`."""


def _coerce_uuid(value: UUID | str | None, field: str) -> UUID | None:
    """Coerce an optional UUID parameter, raising a clean 400 on bad input."""
    if value is None or value == "":
        return None
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationError(f"Field '{field}' must be a valid UUID.") from exc


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
    # --- P7 additions (all additive with defaults) ---
    dry_run: bool = False
    format_version: str = DEFAULT_BACKUP_FORMAT_VERSION
    target_tenant: UUID | None = None
    target_workspace: UUID | None = None
    checksum_verified: bool = False
    warnings: list[str] = field(default_factory=list)
    # ``None`` for a real restore; the exact plan for a dry run.
    plan: dict[str, object] | None = None


def _read_backup_bytes(abs_path: str) -> bytes:
    """Return the backup file's raw bytes, gunzipping dumpdata ``.json.gz``.

    Checksums are computed over the *on-disk* bytes (BackupService hashes the
    gzip payload), while the fixture summary needs the decompressed JSON —
    callers keep both straight by asking for each explicitly.
    """
    with open(abs_path, "rb") as fh:
        raw = fh.read()
    if raw[:2] == b"\x1f\x8b":
        return gzip.decompress(raw)
    return raw


def _summarize_payload(raw: bytes) -> tuple[list[str], dict[str, int]]:
    """Count ``model`` labels in a decoded dumpdata JSON payload."""
    payload = json.loads(raw.decode("utf-8"))
    counts: Counter[str] = Counter(
        obj["model"]
        for obj in payload
        if isinstance(obj, dict) and obj.get("model")
    )
    return sorted(counts), dict(counts)


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
        return _summarize_payload(_read_backup_bytes(abs_path))
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
        dry_run: bool = False,
        target_tenant: UUID | str | None = None,
        target_workspace: UUID | str | None = None,
    ) -> RestoreResult:
        """Restore the database from the named backup (admin-only).

        Args:
            ctx: Caller's auth context; must have the ``admin`` role.
            backup_id: UUID of the :class:`BackupMetadata` to restore.
            confirmation_text: Must be the exact string ``"RESTORE"`` —
                any other value raises :class:`ValidationError` with the
                constant message ``"Captcha mismatch"`` *before* any DB read.
            dry_run: Verify checksum/format/target and return the exact plan
                without calling ``loaddata`` and without writing an audit row.
            target_tenant: Explicit RLS tenant for the restore. Defaults to
                ``ctx.tenant_id``. Must exist.
            target_workspace: Optional destination workspace inside
                ``target_tenant``. Validated and recorded in the audit trail;
                the dumpdata overlay itself remains instance-level (ADR-012).

        Returns:
            A :class:`RestoreResult` describing what was (or would be) restored.

        Raises:
            PermissionDeniedError: Caller lacks the ``admin`` role.
            ValidationError: Bad captcha, bad target, unsupported format or a
                checksum mismatch.
            BackupNotFoundError: Backup/target tenant unknown or not restorable.
        """
        # 1. Admin gate.
        ServiceBase._assert_permission(ctx, "admin")

        # 2. Captcha gate — exact, case-sensitive, before any DB read.
        if confirmation_text != RESTORE_CAPTCHA:
            raise ValidationError("Captcha mismatch")

        # 3. Tenant context (needed to read the backup row and write the audit).
        ServiceBase._set_tenant_context(ctx)

        # 4. Parse the explicit targets up front: a malformed UUID is a 400
        #    before any file work, and never leaves a half-armed RLS context.
        target_tenant_uuid = _coerce_uuid(target_tenant, "target_tenant")
        target_workspace_uuid = _coerce_uuid(target_workspace, "target_workspace")
        warnings: list[str] = []
        cross_tenant = bool(
            target_tenant_uuid and target_tenant_uuid != ctx.tenant_id
        )
        if cross_tenant and not ctx.has_role(ROLE_ADMIN):
            # D16b: cross-tenant is never implicit — the caller must be an
            # admin in the SOURCE context before we even look at a target.
            from application.base import PermissionDeniedError

            raise PermissionDeniedError(
                "Cross-tenant restore requires the admin role"
            )

        # 5. Backup state gate — the row must exist and be 'completed'.
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

        # 6. Format version (P7/D17). Legacy rows without the key are accepted
        #    as the first version; an unknown version is refused before load.
        metadata = dict(backup.metadata or {})
        format_version = str(
            metadata.get("format_version", DEFAULT_BACKUP_FORMAT_VERSION)
        )
        if format_version not in SUPPORTED_FORMAT_VERSIONS:
            raise UnsupportedBackupFormat(
                f"Unsupported backup format_version {format_version!r}; "
                f"supported: {sorted(SUPPORTED_FORMAT_VERSIONS)}."
            )
        if "format_version" not in metadata:
            warnings.append(
                f"Backup row has no format_version; assumed "
                f"{DEFAULT_BACKUP_FORMAT_VERSION}."
            )

        # Snapshot for the audit entry before the body starts.
        snapshot_path = backup.file_path
        restore_event_id = uuid.uuid4()
        started_at = datetime.now(UTC)
        effective_tenant = target_tenant_uuid or ctx.tenant_id

        # 7. Arm RLS for the explicit target and ALWAYS restore the caller's
        #    context in the finally below — a connection is reused across
        #    requests, so leaving the target tenant armed would leak data.
        # 7a. Validate the target under the CALLER's tenant context, before
        #     arming RLS for a possibly non-existent destination. Tenant has
        #     a plain manager, so this lookup is cross-tenant by design.
        if (
            target_tenant_uuid is not None
            and not Tenant.objects.filter(pk=target_tenant_uuid).exists()
        ):
            raise BackupNotFoundError(
                f"Target tenant {target_tenant_uuid} does not exist."
            )

        previous_tenant = (
            TenantContext.get_tenant() if TenantContext.is_set() else None
        )
        rls_armed = False
        try:
            set_request_tenant(effective_tenant)
            rls_armed = True

            if cross_tenant and not UserRole.objects.filter(
                user_id=ctx.user_id, role=ROLE_ADMIN
            ).exists():
                from application.base import PermissionDeniedError

                raise PermissionDeniedError(
                    "Cross-tenant restore requires the admin role in the "
                    "target tenant"
                )

            if target_workspace_uuid is not None and not Workspace.objects.filter(
                pk=target_workspace_uuid, tenant_id=effective_tenant
            ).exists():
                raise ValidationError(
                    f"Target workspace {target_workspace_uuid} does not exist "
                    f"in tenant {effective_tenant}."
                )

            # 8. Resolve the file and verify its checksum BEFORE `loaddata`.
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

            with open(abs_path, "rb") as fh:
                on_disk = fh.read()
            actual_digest = hashlib.sha256(on_disk).hexdigest()
            expected_digest = backup.checksum_sha256
            checksum_verified = False
            if expected_digest:
                if actual_digest != expected_digest:
                    raise BackupChecksumMismatch(
                        f"Backup checksum mismatch: expected {expected_digest}, "
                        f"got {actual_digest}. The file is corrupt or was "
                        "modified after the backup was created."
                    )
                checksum_verified = True
            else:
                warnings.append(
                    "Backup row has no checksum; on-disk integrity could not "
                    "be verified (legacy backup)."
                )

            # 9. Summarize the payload (decompressed) for an honest report.
            #    Informational only — a summary failure never blocks a restore.
            try:
                restored_tables, rows_per_table = _summarize_payload(
                    _read_backup_bytes(abs_path)
                )
            except Exception:  # noqa: BLE001 — diagnostic only
                logger.warning(
                    "AdminRestoreService: could not summarize fixture %s",
                    abs_path,
                    exc_info=True,
                )
                restored_tables, rows_per_table = [], {}

            if cross_tenant and not dry_run:
                # D16b: a cross-tenant restore must be previewed first. The
                # preview writes a durable ``restore.preview`` audit row which
                # is the receipt we check here (24h window).
                from audit.models import AuditEntry
                from datetime import timedelta

                cutoff = datetime.now(UTC) - timedelta(hours=24)
                previewed = AuditEntry.objects.filter(
                    details__operation_kind="restore.preview",
                    details__backup_id=str(backup_id),
                    details__target_tenant=str(effective_tenant),
                    actor=str(ctx.user_id),
                    timestamp__gte=cutoff,
                ).exists()
                if not previewed:
                    raise ValidationError(
                        "Cross-tenant restore requires a dry_run=True preview "
                        "first (valid for 24h)"
                    )

            plan: dict[str, object] = {
                "dry_run": dry_run,
                "backup_id": str(backup_id),
                "format_version": format_version,
                "checksum_verified": checksum_verified,
                "target_tenant": str(effective_tenant),
                "target_workspace": (
                    str(target_workspace_uuid) if target_workspace_uuid else None
                ),
                "restored_tables": restored_tables,
                "rows_per_table": rows_per_table,
                "loaddata": not dry_run,
            }

            if dry_run:
                if cross_tenant:
                    # D16b: the dry-run itself is the audited preview receipt.
                    # Written under the CALLER's tenant (restored below) so the
                    # two tenants each carry one side of the audit trail.
                    ServiceBase._audit(
                        ctx,
                        operation="create",
                        entity_type="BackupRestore",
                        entity_id=restore_event_id,
                        change_reason=f"restore.preview backup_id={backup_id}",
                        details={
                            "operation_kind": "restore.preview",
                            "backup_id": str(backup_id),
                            "source_tenant": str(ctx.tenant_id),
                            "target_tenant": str(effective_tenant),
                            "checksum_verified": checksum_verified,
                            "format_version": format_version,
                        },
                    )
                logger.info(
                    "AdminRestoreService: dry-run complete backup_id=%s",
                    backup_id,
                )
                return RestoreResult(
                    backup_id=backup_id,
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                    restored_tables=restored_tables,
                    rows_per_table=rows_per_table,
                    dry_run=True,
                    format_version=format_version,
                    target_tenant=effective_tenant,
                    target_workspace=target_workspace_uuid,
                    checksum_verified=checksum_verified,
                    warnings=warnings,
                    plan=plan,
                )

            # 10. Real restore: audit 'start' + loaddata + audit 'complete' in
            #     ONE transaction. A failure rolls back the audit rows too.
            try:
                with transaction.atomic():
                    ServiceBase._audit(
                        ctx,
                        operation="create",
                        entity_type="BackupRestore",
                        entity_id=restore_event_id,
                        change_reason=f"restore.start backup_id={backup_id}",
                        details={
                            "operation_kind": "restore.start",
                            "backup_id": str(backup_id),
                            "source_tenant": str(ctx.tenant_id),
                            "backup_type": backup.backup_type,
                            "format_version": format_version,
                            "target_tenant": str(effective_tenant),
                            "target_workspace": (
                                str(target_workspace_uuid)
                                if target_workspace_uuid
                                else None
                            ),
                            "checksum_verified": checksum_verified,
                        },
                    )

                    call_command("loaddata", abs_path, verbosity=0)

                    completed_at = datetime.now(UTC)
                    result = RestoreResult(
                        backup_id=backup_id,
                        started_at=started_at,
                        completed_at=completed_at,
                        restored_tables=restored_tables,
                        rows_per_table=rows_per_table,
                        format_version=format_version,
                        target_tenant=effective_tenant,
                        target_workspace=target_workspace_uuid,
                        checksum_verified=checksum_verified,
                        warnings=warnings,
                        plan=plan,
                    )

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
                            "source_tenant": str(ctx.tenant_id),
                            "duration_seconds": (
                                completed_at - started_at
                            ).total_seconds(),
                            "target_tenant": str(effective_tenant),
                            "target_workspace": (
                                str(target_workspace_uuid)
                                if target_workspace_uuid
                                else None
                            ),
                        },
                    )

                    logger.info(
                        "AdminRestoreService: restore complete backup_id=%s",
                        backup_id,
                    )
                    return result
            except Exception:
                # The single failure audit is written by the outer handler.
                raise
        except Exception as exc:
            # Checksum/format/target refusals also get a best-effort failure
            # audit, consistent with the pre-existing behaviour for loaddata.
            if dry_run:
                raise
            self._record_failure(
                ctx=ctx,
                restore_event_id=restore_event_id,
                backup_id=backup_id,
                error=str(exc),
            )
            raise
        finally:
            if rls_armed:
                if previous_tenant is not None:
                    set_request_tenant(previous_tenant)
                else:
                    clear_request_tenant()

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
        previous = (
            TenantContext.get_tenant() if TenantContext.is_set() else None
        )
        try:
            # The failure may have happened while RLS was armed for a foreign
            # (or even non-existent) target tenant. Audit rows belong to the
            # caller's tenant, so arm that context explicitly first.
            set_request_tenant(ctx.tenant_id)
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
        finally:
            if previous is not None:
                set_request_tenant(previous)
            else:
                clear_request_tenant()


__all__ = [
    "DEFAULT_BACKUP_FORMAT_VERSION",
    "SUPPORTED_FORMAT_VERSIONS",
    "RESTORE_CAPTCHA",
    "AdminRestoreService",
    "BackupChecksumMismatch",
    "RestoreResult",
    "UnsupportedBackupFormat",
]
