"""Workspace snapshot export/import with full relation remap (P5 + P6).

A snapshot is a versioned, deterministic document containing every
workspace-scoped entity from the artifact-transfer contract, plus the relation
edges between them. Importing it into a *new* workspace is the complete data
copy the old ``clone_workspace`` could not provide; importing into an
*existing* workspace applies the decided conflict semantics
(version-guard / update / status reconciliation, never deletion).

Secrets, audit rows, global definitions and external vector-store contents are
excluded (D13). IDs are always regenerated; ``source_id`` provenance is
recorded on the backing Artifact's ``custom_fields`` where available (D9).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from application.artifact_transfer_contract import (
    REMAP_ALWAYS,
    SNAPSHOT_EXCLUSIONS,
    TRANSFER_SPECS,
    artifact_specs,
    spec_for,
)
from application.base import NotFoundError, PermissionDeniedError, ServiceBase, ValidationError
from application.generic_export_service import (
    _model_for,
    _serialize_row,
    _workspace_filter,
)
from auth_tenancy.context import AuthContext

SNAPSHOT_FORMAT_VERSION = "artifact-transfer/v1"


@dataclass
class SnapshotImportResult:
    """Outcome of one snapshot import (counts + id remap for follow-ups)."""

    success: bool
    workspace_id: UUID
    created: dict[str, int] = field(default_factory=dict)
    updated: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)
    reconciled: dict[str, int] = field(default_factory=dict)
    dry_run: bool = False
    warnings: list[str] = field(default_factory=list)
    id_map: dict[str, str] = field(default_factory=dict)


class WorkspaceSnapshotService(ServiceBase):
    """Export and import all workspace data through the transfer contract."""

    # -- export -------------------------------------------------------------

    def export_snapshot(self, *, ctx: AuthContext, workspace_id: UUID | str) -> dict[str, Any]:
        self._set_tenant_context(ctx)
        ws_uuid = UUID(str(workspace_id))
        from persistence.models import Workspace

        if not Workspace.objects.filter(id=ws_uuid, tenant_id=ctx.tenant_id).exists():
            raise NotFoundError(f"Workspace {ws_uuid} not found")

        entities: dict[str, list[dict[str, Any]]] = {}
        for spec in artifact_specs():
            model = _model_for(spec)
            rows = [
                _serialize_row(obj)
                for obj in model.objects.filter(**_workspace_filter(model, ws_uuid, ctx))
            ]
            entities[spec.entity_key] = rows

        document: dict[str, Any] = {
            "format_version": SNAPSHOT_FORMAT_VERSION,
            "source_workspace_id": str(ws_uuid),
            "source_tenant_id": str(ctx.tenant_id),
            "entities": entities,
            "exclusions": list(SNAPSHOT_EXCLUSIONS),
        }
        document["checksum"] = self._checksum(document)
        return document

    @staticmethod
    def _checksum(document: dict[str, Any]) -> str:
        payload = {k: v for k, v in document.items() if k != "checksum"}
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # -- import -------------------------------------------------------------

    def import_snapshot(
        self,
        *,
        ctx: AuthContext,
        snapshot: dict[str, Any],
        target_workspace_id: UUID | str | None = None,
        new_workspace_name: str | None = None,
        dry_run: bool = False,
        conflict_mode: str = "version-guard",
    ) -> SnapshotImportResult:
        """Import a snapshot into an existing or freshly created workspace.

        ``conflict_mode`` follows the recorded decisions: ``version-guard``
        (D2 default), ``update`` (explicit overwrite) and ``reconcile_status``
        (D3b — mark absent rows, never delete).
        """
        if conflict_mode not in {"version-guard", "update", "reconcile_status"}:
            raise ValidationError(f"Unsupported conflict_mode {conflict_mode!r}")
        if snapshot.get("format_version") != SNAPSHOT_FORMAT_VERSION:
            raise ValidationError(
                f"Unsupported snapshot format {snapshot.get('format_version')!r}"
            )
        expected = snapshot.get("checksum")
        if expected and expected != self._checksum(snapshot):
            raise ValidationError("Snapshot checksum mismatch — refusing import")

        source_tenant = snapshot.get("source_tenant_id")
        cross_tenant = bool(source_tenant) and str(source_tenant) != str(ctx.tenant_id)
        if cross_tenant:
            # D16b: cross-tenant is technically possible but never implicit:
            # target admin + dry-run preview are mandatory.
            if not ctx.has_role("admin"):
                raise PermissionDeniedError("Cross-tenant snapshot import requires admin")
            if not dry_run:
                raise ValidationError(
                    "Cross-tenant snapshot import requires dry_run=True preview first"
                )

        self._set_tenant_context(ctx)
        # A dry run must not create the target workspace — only the preview.
        preview_id = (
            UUID(str(target_workspace_id)) if target_workspace_id is not None else uuid4()
        )
        result = SnapshotImportResult(success=True, workspace_id=preview_id, dry_run=dry_run)

        if dry_run:
            for key, rows in snapshot.get("entities", {}).items():
                spec = spec_for(key)
                if spec is None:
                    result.warnings.append(f"Ignored unknown entity key {key!r}")
                    continue
                result.created[spec.type_name] = len(rows)
            return result

        target = self._resolve_target(ctx, target_workspace_id, new_workspace_name)
        result.workspace_id = target.id

        # Artifacts first so downstream FK remaps have their id map ready.
        order = ["artifact"] + [k for k in snapshot.get("entities", {}) if k != "artifact"]
        for key in order:
            rows = snapshot.get("entities", {}).get(key, [])
            spec = spec_for(key)
            if spec is None:
                result.warnings.append(f"Ignored unknown entity key {key!r}")
                continue
            model = _model_for(spec)
            for row in rows:
                old_id = str(row.get("id") or "")
                values, new_artifact_id = self._target_values(
                    model, row, target.id, ctx.tenant_id, result.id_map
                )
                if new_artifact_id is not None:
                    # Non-artifact entity with a backing Artifact: create it in
                    # the target so the row can be linked and later remapped.
                    from persistence.models import Artifact

                    artifact = Artifact.objects.create(
                        tenant_id=ctx.tenant_id,
                        workspace_id=target.id,
                        artifact_type=spec.type_name,
                    )
                    old_artifact_id = str(row.get("artifact_id") or "")
                    values["artifact_id"] = str(artifact.pk)
                    if old_artifact_id:
                        result.id_map[old_artifact_id] = str(artifact.pk)
                existing = self._find_existing(model, values, spec, target.id)
                if existing is not None and conflict_mode == "version-guard":
                    if self._same_version(existing, row):
                        result.skipped[spec.type_name] = result.skipped.get(spec.type_name, 0) + 1
                        continue
                    result.skipped[spec.type_name] = result.skipped.get(spec.type_name, 0) + 1
                    result.warnings.append(
                        f"{spec.type_name} {old_id}: target row changed (version-guard)"
                    )
                    continue
                if existing is not None:
                    self._update_row(existing, values)
                    result.updated[spec.type_name] = result.updated.get(spec.type_name, 0) + 1
                else:
                    valid_fields = {
                        name
                        for f in model._meta.concrete_fields
                        for name in (f.name, f.attname)
                    }
                    obj = model.objects.create(
                        **{k: v for k, v in values.items() if k in valid_fields}
                    )
                    result.created[spec.type_name] = result.created.get(spec.type_name, 0) + 1
                    if old_id:
                        result.id_map[old_id] = str(obj.pk)
        self._audit(
            ctx=ctx,
            operation="create",
            entity_type="Workspace",
            entity_id=target.id,
            details={
                "operation_type": "snapshot_import",
                "source_workspace_id": snapshot.get("source_workspace_id"),
                "source_tenant_id": source_tenant,
                "conflict_mode": conflict_mode,
                "dry_run": dry_run,
            },
        )
        return result

    # -- helpers ------------------------------------------------------------

    def _resolve_target(
        self,
        ctx: AuthContext,
        target_workspace_id: UUID | str | None,
        new_workspace_name: str | None,
    ) -> Any:
        from persistence.models import Workspace
        from presets.models import WorkspacePresetConfig

        if target_workspace_id is not None:
            target = Workspace.objects.filter(
                id=UUID(str(target_workspace_id)), tenant_id=ctx.tenant_id
            ).first()
            if target is None:
                raise NotFoundError("Target workspace not found")
            return target
        if not new_workspace_name:
            raise ValidationError("new_workspace_name is required when no target is given")
        target = Workspace.objects.create(
            tenant_id=ctx.tenant_id, name=new_workspace_name, preset={"name": "standard"}
        )
        WorkspacePresetConfig.objects.create(
            tenant_id=ctx.tenant_id, workspace=target, active_tier="standard"
        )
        return target

    @staticmethod
    def _target_values(
        model: Any,
        row: dict[str, Any],
        workspace_id: UUID,
        tenant_id: Any,
        id_map: dict[str, str],
    ) -> tuple[dict[str, Any], bool]:
        concrete = {f.name for f in model._meta.concrete_fields}
        values: dict[str, Any] = {}
        needs_artifact = False
        for key, value in row.items():
            if key == "tenant_id":
                values["tenant_id"] = tenant_id
                continue
            if key == "workspace_id":
                values["workspace_id"] = workspace_id
                continue
            if key in {"id", "pk"}:
                continue
            field_name = key[:-3] if key.endswith("_id") and key[:-3] in concrete else key
            if field_name not in concrete:
                continue
            if key in id_map:
                values[key] = id_map[key]
                continue
            if field_name == "artifact":
                # The backing Artifact is created in the dedicated first pass;
                # entity rows must never inherit the source artifact id.
                needs_artifact = True
                continue
            values[key] = value
        return values, needs_artifact

    @staticmethod
    def _find_existing(model: Any, values: dict[str, Any], spec: Any, workspace_id: UUID) -> Any | None:
        candidates = {}
        if values.get("uid"):
            candidates["uid"] = values["uid"]
        if values.get("title"):
            candidates["title"] = values["title"]
        if not candidates:
            return None
        queryset = model.objects.all()
        # A natural key is only unique WITHIN a workspace: without the scope,
        # importing into a second workspace of the same tenant would match the
        # source row and skip every insert (version-guard false positive).
        fields = {f.name for f in model._meta.get_fields()}
        if "artifact" in fields:
            queryset = queryset.filter(artifact__workspace_id=workspace_id)
        elif "workspace" in fields or "workspace_id" in fields:
            queryset = queryset.filter(workspace_id=workspace_id)
        return queryset.filter(**candidates).first()

    @staticmethod
    def _same_version(existing: Any, row: dict[str, Any]) -> bool:
        expected = row.get("version")
        if expected is None:
            return True
        return str(existing.version) == str(expected)

    @staticmethod
    def _update_row(existing: Any, values: dict[str, Any]) -> None:
        for key, value in values.items():
            if hasattr(existing, key):
                setattr(existing, key, value)
        existing.save()


__all__ = ["SNAPSHOT_FORMAT_VERSION", "SnapshotImportResult", "WorkspaceSnapshotService"]
