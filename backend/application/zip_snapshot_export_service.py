"""Versioned ZIP full-snapshot export (R1/P5, decisions D14a/D14b/D14c/D16).

Complements :mod:`application.workspace_snapshot_service`: that service
produces one in-memory JSON document, this one writes a streamable, checksummed
ZIP to ``EXPORT_DIR`` in a Celery worker and tracks it through an
:class:`~admin_ops.models.ExportSnapshotMetadata` row.

Every one of the 24 entities in :data:`~application.artifact_transfer_contract.TRANSFER_SPECS`
gets its own JSONL bucket (including the two configuration entities, whose
rows may be empty for a given workspace). A ``manifest.json``, a
``relations.jsonl`` edge list, a reserved ``media/`` prefix and a
``checksum.sha256`` sidecar complete the archive. Secrets, audit rows and
global definitions stay excluded (D13).

Cross-tenant transfers are never implicit (D16): the source needs an explicit
read grant (or admin), an explicitly named target needs admin, and a
source/target tenant change requires a dry-run preview before a real export is
queued. Both tenants receive an audit entry.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Iterator
from uuid import UUID, uuid4

from django.utils import timezone

from admin_ops.models import ExportSnapshotMetadata, ExportStatus
from admin_ops.services.paths import absolute_export_path, export_root
from application.artifact_transfer_contract import (
    SNAPSHOT_EXCLUSIONS,
    TRANSFER_SPECS,
)
from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ServiceBase,
    ValidationError,
)
from application.generic_export_service import (
    _model_for,
    _serialize_row,
    _workspace_filter,
)
# Import-cycle guard (#ARCH): workspace_snapshot_service is part of the big
# application SCC; importing it at module level would pull this service into
# that cycle. The service class is imported lazily where it is used, and the
# wire format version is a contract constant shared by both services.
SNAPSHOT_FORMAT_VERSION = "artifact-transfer/v1"
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.tenancy import TenantContext
from presets.exceptions import CrossTenantWorkspaceError

#: Default lifetime of a finished export (24 h). Override with
#: ``EXPORT_SNAPSHOT_TTL_SECONDS``; ``0`` disables expiry (TTL cleanup skips rows
#: with ``expires_at=None``).
_TTL_ENV_VAR = "EXPORT_SNAPSHOT_TTL_SECONDS"
_DEFAULT_TTL_SECONDS = 86_400

#: Reserved archive members that are not entity buckets.
_MANIFEST = "manifest.json"
_RELATIONS = "relations.jsonl"
_MEDIA_NOTICE = "media/README.md"
_CHECKSUM = "checksum.sha256"

_MEDIA_NOTICE_TEXT = (
    "Artifact snapshots carry structured data only (D13). The media/ prefix is "
    "reserved for future binary payloads; no secrets, audit rows, embeddings or "
    "external vector-store contents are part of this archive.\n"
)


def export_ttl_seconds() -> int:
    """Return the configured TTL in seconds (environment-driven, Twelve-Factor)."""
    raw = os.environ.get(_TTL_ENV_VAR, "").strip()
    if not raw:
        return _DEFAULT_TTL_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_TTL_SECONDS
    return max(value, 0)


@dataclass
class ZipExportStatus:
    """Transport-neutral status payload of one export row."""

    export_id: str
    status: str
    source_workspace_id: str
    format_version: str
    checksum_sha256: str | None = None
    content_checksum_sha256: str | None = None
    size_bytes: int | None = None
    expires_at: str | None = None
    download_url: str | None = None
    error_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class ZipSnapshotExportService(ServiceBase):
    """Start, track, stream and verify versioned ZIP workspace snapshots."""

    # -- request path ------------------------------------------------------

    def start_export(
        self,
        *,
        ctx: AuthContext,
        workspace_id: UUID | str,
        target_workspace_id: UUID | str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Gate, preview and queue one export.

        A dry run never persists an export row or queues work; it returns the
        per-entity row counts so a caller can review the scope first. Cross-tenant
        transfers are only ever returned as such a preview.
        """
        source = self._resolve_workspace(workspace_id)
        self._assert_source_read(ctx, source)

        target = (
            self._resolve_workspace(target_workspace_id)
            if target_workspace_id is not None
            else None
        )
        cross_tenant = bool(
            target is not None and str(target.tenant_id) != str(source.tenant_id)
        )
        if cross_tenant:
            # D16: target ADMIN is mandatory, and a real (non-preview) transfer
            # needs the dry-run review first — the same shape the JSON snapshot
            # importer uses.
            self._assert_target_admin(ctx, target)
            if not dry_run:
                raise ValidationError(
                    "Cross-tenant snapshot export requires a dry_run=True "
                    "preview before the real export is queued"
                )

        if dry_run:
            preview = self._preview(ctx, source)
            self._audit_bidirectional(
                ctx=ctx,
                source=source,
                target=target,
                entity_id=source.id,
                operation="export_snapshot_preview",
                details={
                    "source_workspace_id": str(source.id),
                    "target_workspace_id": str(target.id) if target else None,
                    "cross_tenant": cross_tenant,
                    "entity_counts": preview,
                },
            )
            return {
                "dry_run": True,
                "source_workspace_id": str(source.id),
                "target_workspace_id": str(target.id) if target else None,
                "cross_tenant": cross_tenant,
                "preview": preview,
            }

        self._set_tenant_context(ctx)
        ttl = export_ttl_seconds()
        now = timezone.now()
        expires_at = now + timedelta(seconds=ttl) if ttl > 0 else None
        export_id = uuid4()
        provenance: dict[str, Any] = {
            "source_tenant_id": str(source.tenant_id),
            "format_version": SNAPSHOT_FORMAT_VERSION,
        }
        if target is not None:
            provenance["target_workspace_id"] = str(target.id)
            provenance["target_tenant_id"] = str(target.tenant_id)

        row = ExportSnapshotMetadata.objects.create(
            id=export_id,
            tenant_id=ctx.tenant_id,
            owner_id=ctx.user_id,
            created_by_id=ctx.user_id,
            status=ExportStatus.PENDING,
            source_workspace_id=source.id,
            file_path=f"{export_id}.zip",
            expires_at=expires_at,
            format_version=SNAPSHOT_FORMAT_VERSION,
            metadata=provenance,
        )

        from application.tasks import export_workspace_snapshot_zip

        task = export_workspace_snapshot_zip.delay(
            str(row.id),
            str(ctx.tenant_id),
            str(source.id),
            str(source.tenant_id),
        )
        row.task_id = str(task.id)
        row.save(update_fields=["task_id", "modified_at"])

        self._audit_bidirectional(
            ctx=ctx,
            source=source,
            target=target,
            entity_id=row.id,
            operation="export_snapshot_started",
            details={
                "export_id": str(row.id),
                "task_id": str(task.id),
                "source_workspace_id": str(source.id),
                "target_workspace_id": str(target.id) if target else None,
                "cross_tenant": cross_tenant,
                "expires_at": expires_at.isoformat() if expires_at else None,
            },
        )
        # The eager test worker has already finished by this point; a real
        # deployment reports 'pending' until the worker picks the job up.
        row.refresh_from_db()
        return {
            "export_id": str(row.id),
            "task_id": str(task.id),
            "status": row.status,
            "checksum_sha256": row.checksum_sha256,
            "size_bytes": row.size_bytes,
            "status_url": (
                f"/api/v1/workspaces/{source.id}/export/snapshot/zip/{row.id}/status/"
            ),
            "download_url": (
                f"/api/v1/workspaces/{source.id}/export/snapshot/zip/{row.id}/download/"
            ),
        }

    def get_status(
        self,
        *,
        ctx: AuthContext,
        workspace_id: UUID | str,
        export_id: UUID | str,
    ) -> ZipExportStatus:
        """Return the tracked status of one export (tenant- and workspace-bound)."""
        row = self._scoped_export(ctx, workspace_id, export_id)
        return ZipExportStatus(
            export_id=str(row.id),
            status=row.status,
            source_workspace_id=str(row.source_workspace_id),
            format_version=row.format_version,
            checksum_sha256=row.checksum_sha256,
            content_checksum_sha256=row.content_checksum_sha256,
            size_bytes=row.size_bytes,
            expires_at=row.expires_at.isoformat() if row.expires_at else None,
            download_url=(
                f"/api/v1/workspaces/{row.source_workspace_id}/export/snapshot/zip/"
                f"{row.id}/download/"
                if row.is_downloadable
                else None
            ),
            error_message=row.error_message or "",
            metadata=row.metadata or {},
        )

    def download_path(
        self,
        *,
        ctx: AuthContext,
        workspace_id: UUID | str,
        export_id: UUID | str,
    ) -> str:
        """Resolve the absolute ZIP path, refusing missing/expired exports."""
        row = self._scoped_export(ctx, workspace_id, export_id)
        if not row.is_downloadable or not row.file_path:
            raise ValidationError("Export is not downloadable (not completed or expired)")
        path = absolute_export_path(row.file_path)
        if not os.path.isfile(path):
            raise NotFoundError("Export file is missing")
        return path

    # -- worker path -------------------------------------------------------

    def build_zip(
        self,
        *,
        export_id: UUID | str,
        tenant_id: UUID | str,
        workspace_id: UUID | str,
        source_tenant_id: UUID | str,
    ) -> dict[str, Any]:
        """Stream one snapshot into the ZIP and stamp its metadata row.

        Called only from :func:`application.tasks.export_workspace_snapshot_zip`.
        Only ids cross the queue boundary; the worker re-arms the tenant context
        before this method runs. Failures are recorded on the row and re-raised
        so Celery reports FAILURE.
        """
        from persistence.middleware import set_request_tenant

        row = ExportSnapshotMetadata.objects.get(id=UUID(str(export_id)))
        row.status = ExportStatus.IN_PROGRESS
        row.save(update_fields=["status", "modified_at", "version"])

        source_ctx = AuthContext(
            user_id=row.owner_id or uuid4(),
            tenant_id=UUID(str(source_tenant_id)),
            active_roles=(),
            auth_method=AuthMethod.BEARER_TOKEN,
            workspace_id=UUID(str(workspace_id)),
        )

        tmp_path: str | None = None
        try:
            # Reuse the JSON snapshot's row collection so the two transports
            # stay byte-for-byte consistent in what they consider in scope.
            from application.workspace_snapshot_service import WorkspaceSnapshotService

            snapshot = WorkspaceSnapshotService().export_snapshot(
                ctx=source_ctx, workspace_id=workspace_id
            )
            # export_snapshot armed the SOURCE tenant (ORM layer); restore BOTH
            # isolation layers to the caller's tenant before further queries
            # (ADR-03).
            set_request_tenant(UUID(str(tenant_id)))

            os.makedirs(export_root(), exist_ok=True)
            with tempfile.NamedTemporaryFile(
                dir=export_root(), prefix="export-", suffix=".zip", delete=False
            ) as handle:
                tmp_path = handle.name

            entity_counts, content_checksum = self._write_archive(
                tmp_path, snapshot, source_ctx, workspace_id
            )

            file_checksum = self._file_checksum(tmp_path)
            size = os.path.getsize(tmp_path)
            os.replace(tmp_path, absolute_export_path(row.file_path or f"{row.id}.zip"))
            tmp_path = None

            row.status = ExportStatus.COMPLETED
            row.checksum_sha256 = file_checksum
            row.content_checksum_sha256 = content_checksum
            row.size_bytes = size
            row.completed_at = datetime.now(UTC)
            row.error_message = ""
            row.metadata = {
                **(row.metadata or {}),
                "entity_counts": entity_counts,
                "format_version": SNAPSHOT_FORMAT_VERSION,
            }
            row.save(
                update_fields=[
                    "status",
                    "checksum_sha256",
                    "content_checksum_sha256",
                    "size_bytes",
                    "completed_at",
                    "error_message",
                    "metadata",
                    "modified_at",
                    "version",
                ]
            )
            return {
                "export_id": str(row.id),
                "status": row.status,
                "checksum_sha256": file_checksum,
                "content_checksum_sha256": content_checksum,
                "size_bytes": size,
                "entity_counts": entity_counts,
            }
        except Exception as exc:
            row.status = ExportStatus.FAILED
            row.error_message = str(exc)[:2000]
            row.save(update_fields=["status", "error_message", "modified_at", "version"])
            raise
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:  # pragma: no cover - best-effort cleanup
                    pass

    def _write_archive(
        self,
        path: str,
        snapshot: dict[str, Any],
        source_ctx: AuthContext,
        workspace_id: UUID | str,
    ) -> tuple[dict[str, int], str]:
        """Write all ZIP members; return per-entity counts and content digest."""
        ws_uuid = UUID(str(workspace_id))
        entities: dict[str, list[dict[str, Any]]] = {}
        for spec in TRANSFER_SPECS.values():
            rows = snapshot.get("entities", {}).get(spec.entity_key)
            if rows is None:
                rows = self._extra_rows(spec, ws_uuid, source_ctx)
            entities[spec.entity_key] = rows

        digest = hashlib.sha256()
        counts: dict[str, int] = {}
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for key, rows in entities.items():
                filename = f"entities/{key}.jsonl"
                count = 0
                with archive.open(filename, "w", force_zip64=True) as stream:
                    for row in rows:
                        line = self._json_line(row)
                        stream.write(line)
                        digest.update(filename.encode("utf-8"))
                        digest.update(line)
                        count += 1
                counts[key] = count

            relations = list(self._relation_rows(entities))
            with archive.open(_RELATIONS, "w", force_zip64=True) as stream:
                for relation in relations:
                    line = self._json_line(relation)
                    stream.write(line)
                    digest.update(_RELATIONS.encode("utf-8"))
                    digest.update(line)

            media_bytes = _MEDIA_NOTICE_TEXT.encode("utf-8")
            with archive.open(_MEDIA_NOTICE, "w", force_zip64=True) as stream:
                stream.write(media_bytes)
            digest.update(_MEDIA_NOTICE.encode("utf-8"))
            digest.update(media_bytes)

            content_checksum = digest.hexdigest()
            with archive.open(_CHECKSUM, "w", force_zip64=True) as stream:
                stream.write(content_checksum.encode("ascii"))

            manifest = {
                "format_version": SNAPSHOT_FORMAT_VERSION,
                "source_workspace_id": str(ws_uuid),
                "source_tenant_id": str(source_ctx.tenant_id),
                "generated_at": datetime.now(UTC).isoformat(),
                "entities": {
                    key: {"file": f"entities/{key}.jsonl", "count": count}
                    for key, count in counts.items()
                },
                "relations": {"file": _RELATIONS, "count": len(relations)},
                "media": {"prefix": "media/", "files": [_MEDIA_NOTICE]},
                "exclusions": list(SNAPSHOT_EXCLUSIONS),
                "checksum": content_checksum,
            }
            with archive.open(_MANIFEST, "w", force_zip64=True) as stream:
                stream.write(
                    json.dumps(
                        manifest, sort_keys=True, ensure_ascii=False, default=str
                    ).encode("utf-8")
                )
        return counts, content_checksum

    @staticmethod
    def _extra_rows(
        spec: Any, workspace_id: UUID, ctx: AuthContext
    ) -> list[dict[str, Any]]:
        """Rows for the two config entities the JSON snapshot does not carry."""
        try:
            model = _model_for(spec)
            queryset = model.objects.filter(**_workspace_filter(model, workspace_id, ctx))
            return [_serialize_row(obj) for obj in queryset]
        except Exception:  # noqa: BLE001 - a config entity may be unscoped here
            return []

    @staticmethod
    def _json_line(row: dict[str, Any]) -> bytes:
        return (
            json.dumps(row, sort_keys=True, ensure_ascii=False, default=str) + "\n"
        ).encode("utf-8")

    @staticmethod
    def _relation_rows(
        entities: dict[str, list[dict[str, Any]]]
    ) -> Iterator[dict[str, Any]]:
        """Derive a flat edge list from serialized relation carriers (D10)."""
        seen: set[str] = set()
        for entity_key, rows in entities.items():
            for row in rows:
                for field_name in ("source_id", "target_id", "parent_id", "artifact_id"):
                    related = row.get(field_name)
                    if related in (None, ""):
                        continue
                    edge = {
                        "kind": entity_key,
                        "relation": field_name,
                        "entity_id": str(row.get("id") or ""),
                        "related_id": str(related),
                        "link_type": row.get("link_type"),
                    }
                    key = json.dumps(edge, sort_keys=True, default=str)
                    if key not in seen:
                        seen.add(key)
                        yield edge

    @staticmethod
    def _file_checksum(path: str) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    # -- verification / TTL ------------------------------------------------

    def verify_zip_checksum(
        self, path: str, expected_checksum: str | None = None
    ) -> bool:
        """Verify the stored ZIP checksum and its internal content digest.

        Raises :class:`ValidationError` on any mismatch — a corrupted archive is
        never silently accepted (D14b checksum gate).
        """
        if not os.path.isfile(path):
            raise NotFoundError("Export file is missing")
        if expected_checksum:
            actual = self._file_checksum(path)
            if actual != expected_checksum:
                raise ValidationError("Snapshot checksum mismatch — refusing download")
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if _MANIFEST not in names or _CHECKSUM not in names:
                raise ValidationError("Snapshot checksum mismatch — archive incomplete")
            stored = archive.read(_CHECKSUM).decode("ascii").strip()
            manifest = json.loads(archive.read(_MANIFEST).decode("utf-8"))
            if manifest.get("checksum") != stored:
                raise ValidationError("Snapshot checksum mismatch — manifest diverged")
            recomputed = self._content_checksum(archive)
            if recomputed != stored:
                raise ValidationError("Snapshot checksum mismatch — contents changed")
        return True

    @staticmethod
    def _content_checksum(archive: zipfile.ZipFile) -> str:
        """Recompute the content digest in the exact order used by the writer.

        JSONL members are folded in per line (with their name repeated), all
        other members once — mirroring :meth:`_write_archive` byte for byte.
        """
        digest = hashlib.sha256()
        names = [
            f"entities/{spec.entity_key}.jsonl" for spec in TRANSFER_SPECS.values()
        ] + [_RELATIONS, _MEDIA_NOTICE]
        present = set(archive.namelist())
        for name in names:
            if name not in present:
                continue
            data = archive.read(name)
            if name.endswith(".jsonl"):
                for line in data.splitlines(keepends=True):
                    digest.update(name.encode("utf-8"))
                    digest.update(line)
            else:
                digest.update(name.encode("utf-8"))
                digest.update(data)
        return digest.hexdigest()

    # -- gates / helpers ---------------------------------------------------

    @staticmethod
    def _resolve_workspace(workspace_id: UUID | str) -> Any:
        from persistence.models import Workspace

        try:
            ws_uuid = UUID(str(workspace_id))
        except (ValueError, TypeError) as exc:
            raise ValidationError("Invalid workspace id") from exc
        workspace = Workspace.unscoped.filter(id=ws_uuid).first()
        if workspace is None:
            raise NotFoundError(f"Workspace {ws_uuid} not found")
        return workspace

    @staticmethod
    def _assert_source_read(ctx: AuthContext, source: Any) -> None:
        """Source READ gate (D16): in-tenant membership or explicit grant/admin."""
        if str(source.tenant_id) == str(ctx.tenant_id):
            read_roles = {"viewer", "editor", "admin", "approver"}
            if not any(ctx.has_role(role) for role in read_roles):
                raise PermissionDeniedError("Source workspace read is not permitted")
            return
        granted = str(source.id) in set(ctx.api_key_workspace_ids or ())
        if not granted and not ctx.has_role("admin"):
            raise CrossTenantWorkspaceError(
                "Cross-tenant source export requires an explicit read grant or admin"
            )

    @staticmethod
    def _assert_target_admin(ctx: AuthContext, target: Any) -> None:
        """Target ADMIN gate (D16) for a cross-tenant destination."""
        if not ctx.has_role("admin"):
            raise PermissionDeniedError(
                "Cross-tenant snapshot export requires target admin"
            )

    def _preview(self, ctx: AuthContext, source: Any) -> dict[str, int]:
        """Per-entity row counts without writing anything (cross-tenant safe)."""
        from persistence.middleware import clear_request_tenant, set_request_tenant

        source_ctx = AuthContext(
            user_id=ctx.user_id,
            tenant_id=source.tenant_id,
            active_roles=ctx.active_roles,
            auth_method=ctx.auth_method,
            actor_type=ctx.actor_type,
            agent_label=ctx.agent_label,
            workspace_id=source.id,
        )
        previous = TenantContext.get_tenant() if TenantContext.is_set() else None
        set_request_tenant(source.tenant_id)
        try:
            from application.workspace_snapshot_service import WorkspaceSnapshotService

            snapshot = WorkspaceSnapshotService().export_snapshot(
                ctx=source_ctx, workspace_id=source.id
            )
        finally:
            if previous is None:
                clear_request_tenant()
            else:
                set_request_tenant(previous)
        return {
            key: len(rows) for key, rows in snapshot.get("entities", {}).items()
        }

    def _scoped_export(
        self, ctx: AuthContext, workspace_id: UUID | str, export_id: UUID | str
    ) -> ExportSnapshotMetadata:
        self._set_tenant_context(ctx)
        try:
            export_uuid = UUID(str(export_id))
        except (ValueError, TypeError) as exc:
            raise ValidationError("Invalid export id") from exc
        row = ExportSnapshotMetadata.objects.filter(id=export_uuid).first()
        if row is None or str(row.source_workspace_id) != str(workspace_id):
            raise NotFoundError("Export not found")
        return row

    def _audit_bidirectional(
        self,
        *,
        ctx: AuthContext,
        source: Any,
        target: Any,
        entity_id: UUID,
        operation: str,
        details: dict[str, Any],
    ) -> None:
        """Write one audit entry per involved tenant (D16, both directions)."""
        previous = TenantContext.get_tenant() if TenantContext.is_set() else None
        try:
            source_ctx = AuthContext(
                user_id=ctx.user_id,
                tenant_id=source.tenant_id,
                active_roles=ctx.active_roles,
                auth_method=ctx.auth_method,
                actor_type=ctx.actor_type,
                agent_label=ctx.agent_label,
                workspace_id=source.id,
            )
            TenantContext.set_tenant(source.tenant_id)
            self._audit(
                source_ctx,
                operation="create",
                entity_type="Workspace",
                entity_id=entity_id,
                change_reason=operation,
                details={"side": "source", **details},
            )
            if target is not None and str(target.tenant_id) != str(source.tenant_id):
                target_ctx = AuthContext(
                    user_id=ctx.user_id,
                    tenant_id=target.tenant_id,
                    active_roles=ctx.active_roles,
                    auth_method=ctx.auth_method,
                    actor_type=ctx.actor_type,
                    agent_label=ctx.agent_label,
                    workspace_id=target.id,
                )
                TenantContext.set_tenant(target.tenant_id)
                self._audit(
                    target_ctx,
                    operation="create",
                    entity_type="Workspace",
                    entity_id=entity_id,
                    change_reason=operation,
                    details={"side": "target", **details},
                )
        finally:
            if previous is None:
                TenantContext.clear_tenant()
            else:
                TenantContext.set_tenant(previous)


def purge_expired_exports(*, now: datetime | None = None) -> int:
    """Delete expired export rows and their ZIP files (D14b TTL cleanup).

    Uses the explicit ``unscoped`` manager: this is a system-maintenance sweep
    across tenants, invoked only by the Celery cleanup task. Files are removed
    best-effort so a stale file never blocks row cleanup.
    """
    cutoff = now or timezone.now()
    expired = list(ExportSnapshotMetadata.unscoped.filter(expires_at__lt=cutoff))
    removed = 0
    for row in expired:
        if row.file_path:
            try:
                os.remove(absolute_export_path(row.file_path))
            except OSError:
                pass
        row.delete()
        removed += 1
    return removed


__all__ = [
    "SNAPSHOT_FORMAT_VERSION",
    "ZipExportStatus",
    "ZipSnapshotExportService",
    "export_ttl_seconds",
    "purge_expired_exports",
]
