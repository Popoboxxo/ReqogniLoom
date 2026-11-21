"""Workspace snapshot export/import with full relation remap (P5 + P6).

A snapshot is a versioned, deterministic document containing every
workspace-scoped entity from the artifact-transfer contract, plus the relation
edges between them. Importing it into a *new* workspace is the complete data
copy the old ``clone_workspace`` could not provide; importing into an
*existing* workspace applies the decided conflict semantics
(version-guard / update / status reconciliation, never deletion).

Secrets, audit rows, global definitions and external vector-store contents are
excluded (D13). IDs are always regenerated; provenance is recorded on the
backing Artifact's ``copied_from`` FK (D9), with an opt-in
``custom_fields["source_id"]`` stamp for full workspace copies.
"""
from __future__ import annotations

import uuid

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from application.artifact_transfer_contract import (
    ARTIFACT_RELATIONS,
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

#: Plain ``UUIDField`` columns that nevertheless hold an Artifact id and must
#: therefore be remapped on copy. Icd declares its endpoints as UUIDFields,
#: not FKs (see icd/models.py), so the generic `field.is_relation` check cannot
#: discover them. Goal.lineage_id is deliberately NOT in this set: it is a
#: logical grouping that must get a fresh identity in the target.
PLAIN_UUID_REFERENCES = frozenset({"source_element_id", "target_element_id"})

#: Relation carriers that are *not* themselves transfer entities. The entity
#: loop already copies trace_links / allocation / group_membership (TraceLink),
#: comments (Comment), parent_hierarchy (Artifact/ArchitectureElement) and
#: test_runs (TestRun). Only the join row that connects a TestRun to a TestCase
#: has no spec of its own, so it is copied in the relation pass below (D10).
_EXTRA_RELATION_MODELS: dict[str, str] = {
    "test_runs": "persistence.TestRunResult",
}


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
        stamp_source_id: bool = False,
    ) -> SnapshotImportResult:
        """Import a snapshot into an existing or freshly created workspace.

        ``conflict_mode`` follows the recorded decisions: ``version-guard``
        (D2 default), ``update`` (explicit overwrite) and ``reconcile_status``
        (D3b — mark absent rows, never delete).

        Every row is re-inserted with a fresh primary key. All references are
        replayed through ``id_map`` (D9/D10/D12b): identity columns listed in
        ``REMAP_ALWAYS`` always point at the target tenant/workspace, and every
        other FK/M2M target is remapped when it names a source row that was
        imported. References to shared rows (users, actors, API keys) are kept.
        The entity set comes from the transfer contract — there is no per-type
        copy branch here, so adding an entity needs no import-side change.

        ``stamp_source_id`` adds ``custom_fields["source_id"]`` to the cloned
        rows. It is opt-in because that is a *mutation* of an authoritative
        field: a plain field-parity round trip must reproduce the source value
        byte-for-byte. ``clone_workspace`` enables it for provenance (D9); the
        canonical provenance FK ``Artifact.copied_from`` is always set.
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

        # Artifacts first so the entity rows can resolve their backing id.
        # Unknown keys are appended so they are reported deterministically.
        entities = snapshot.get("entities", {})
        known = [key for key in TRANSFER_SPECS if key in entities]
        order = ["artifact"] + [key for key in known if key != "artifact"]
        order += [key for key in entities if key not in order]

        created_rows: list[tuple[str, str, Any]] = []
        pending: list[tuple[Any, dict[str, str]]] = []
        new_identity = str(snapshot.get("source_workspace_id")) != str(target.id)

        for key in order:
            rows = entities.get(key, [])
            spec = spec_for(key)
            if spec is None:
                result.warnings.append(f"Ignored unknown entity key {key!r}")
                continue
            model = _model_for(spec)
            for row in rows:
                old_id = str(row.get("id") or "")
                values, deferred = self._target_values(
                    model,
                    row,
                    target.id,
                    ctx.tenant_id,
                    result.id_map,
                    new_identity=new_identity,
                )
                if key == "artifact" and old_id:
                    # D9/D7: an artifact created from this source already has
                    # the source id as provenance. Reusing it on a replay keeps
                    # the import idempotent without a natural key on Artifact.
                    from persistence.models import Artifact

                    reused = Artifact.objects.filter(
                        workspace_id=target.id, copied_from_id=old_id
                    ).first()
                    if reused is not None:
                        result.id_map[old_id] = str(reused.pk)
                        result.skipped["Artifact"] = result.skipped.get("Artifact", 0) + 1
                        continue
                    if str(snapshot.get("source_tenant_id")) == str(ctx.tenant_id):
                        values["copied_from_id"] = old_id
                if old_id and stamp_source_id:
                    self._stamp_provenance(model, values, old_id)

                existing = self._find_existing(model, values, spec, target.id)
                if existing is not None and conflict_mode == "version-guard":
                    result.skipped[spec.type_name] = result.skipped.get(spec.type_name, 0) + 1
                    if not self._same_version(existing, row):
                        result.warnings.append(
                            f"{spec.type_name} {old_id}: target row changed (version-guard)"
                        )
                    continue

                if existing is not None:
                    self._update_row(existing, values)
                    instance = existing
                    result.updated[spec.type_name] = result.updated.get(spec.type_name, 0) + 1
                else:
                    valid_fields = {
                        name
                        for field in model._meta.concrete_fields
                        for name in (field.name, field.attname)
                    }
                    instance = model.objects.create(
                        **{k: v for k, v in values.items() if k in valid_fields}
                    )
                    result.created[spec.type_name] = result.created.get(spec.type_name, 0) + 1

                if old_id:
                    result.id_map[old_id] = str(instance.pk)
                if deferred:
                    pending.append((instance, deferred))
                created_rows.append((key, old_id, instance))

        # Second pass: every source row now has a new id, so replay references
        # that pointed forward (≥2-level parent chains, self references).
        for instance, deferred in pending:
            changes = {
                field_key: result.id_map.get(old_value, old_value)
                for field_key, old_value in deferred.items()
            }
            if not changes:
                continue
            name_by_attname = {
                field.attname: field.name for field in instance._meta.concrete_fields
            }
            for field_key, value in changes.items():
                setattr(instance, field_key, value)
            instance.save(update_fields=[name_by_attname.get(key, key) for key in changes])

        self._copy_extra_relations(
            ctx=ctx,
            snapshot=snapshot,
            created_rows=created_rows,
            id_map=result.id_map,
            target=target,
        )
        self._copy_many_to_many(snapshot=snapshot, created_rows=created_rows, id_map=result.id_map)
        if conflict_mode == "reconcile_status":
            self._reconcile_absent_rows(
                ctx=ctx,
                snapshot=snapshot,
                target=target,
                created_rows=created_rows,
                result=result,
            )

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

    def _target_values(
        self,
        model: Any,
        row: dict[str, Any],
        workspace_id: UUID,
        tenant_id: Any,
        id_map: dict[str, str],
        *,
        ensure_artifact: bool = True,
        new_identity: bool = False,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Return target field values and the references still needing a remap.

        ``REMAP_ALWAYS`` identity columns are rebound to the target here. Every
        foreign key whose source id is already in ``id_map`` is remapped
        immediately; the rest are deferred to the caller's second pass (forward
        references in parent chains). Values that are *not* source ids — shared
        users, actors, API keys — are deliberately kept unchanged.
        """
        concrete = {field.name for field in model._meta.concrete_fields}
        attnames = {field.attname for field in model._meta.concrete_fields}
        values: dict[str, Any] = {}
        deferred: dict[str, str] = {}
        for key, value in row.items():
            if key in {"id", "pk"}:
                continue
            if key in REMAP_ALWAYS:
                if key == "tenant_id":
                    values[key] = tenant_id
                elif key == "workspace_id":
                    values[key] = workspace_id
                elif value in (None, ""):
                    continue
                else:
                    old = str(value)
                    mapped = id_map.get(old)
                    if mapped is not None:
                        values[key] = mapped
                    elif key == "artifact_id" and ensure_artifact:
                        # A snapshot without an artifact bucket still needs a
                        # valid backing row; create a minimal replacement here.
                        from persistence.models import Artifact

                        artifact = Artifact.objects.create(
                            tenant_id=tenant_id,
                            workspace_id=workspace_id,
                            artifact_type=str(row.get("artifact_type") or model.__name__),
                            custom_fields={"source_id": old},
                        )
                        values[key] = str(artifact.pk)
                        id_map[old] = str(artifact.pk)
                    else:
                        deferred[key] = old
                continue
            # Goal.lineage_id groups immutable versions of one logical goal.
            # Copying it verbatim into another workspace collides with the
            # (lineage_id, sequence_number) unique constraint; mint one stable
            # replacement per source lineage and reuse it for every version.
            if key == "lineage_id" and value and new_identity:
                lineage_key = f"lineage:{value}"
                mapped = id_map.get(lineage_key)
                if mapped is None:
                    mapped = str(uuid.uuid4())
                    id_map[lineage_key] = mapped
                values[key] = mapped
                continue
            # Only REAL foreign keys (plus the declared plain-UUID references)
            # are remapped. A plain UUIDField like Goal.lineage_id must never
            # be deferred as a reference — that leaves a NOT NULL column empty.
            fk_field = next(
                (
                    f
                    for f in model._meta.concrete_fields
                    if f.attname == key or f.name == key
                ),
                None,
            )
            if (
                key.endswith("_id")
                and fk_field is not None
                and (fk_field.is_relation or key in PLAIN_UUID_REFERENCES)
                and (key in attnames or key[:-3] in concrete)
            ):
                if value in (None, ""):
                    continue
                old = str(value)
                mapped = id_map.get(old)
                if mapped is not None:
                    values[key] = mapped
                else:
                    deferred[key] = old
                    if key in PLAIN_UUID_REFERENCES:
                        # NOT NULL plain-UUID reference (Icd endpoints) whose
                        # target is outside the snapshot: keep the original
                        # value for the insert; the second pass still retries
                        # the remap once every id is known.
                        values[key] = value
                continue
            if key in concrete or key in attnames:
                values[key] = value
        return values, deferred

    @staticmethod
    def _find_existing(model: Any, values: dict[str, Any], spec: Any, workspace_id: UUID) -> Any | None:
        # uid is the identity (D1); combining it with title makes an update
        # invisible when the title changed in the source — the insert then
        # collides with the workspace/uid unique constraint. Fall back to
        # title only when the entity has no uid at all.
        if values.get("uid"):
            candidates: dict[str, Any] = {"uid": values["uid"]}
        elif values.get("title"):
            candidates = {"title": values["title"]}
        else:
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

    @staticmethod
    def _stamp_provenance(model: Any, values: dict[str, Any], old_id: str) -> None:
        """Record D9 provenance on rows that carry a ``custom_fields`` map.

        The backing Artifact of every artifact-scoped entity receives
        ``custom_fields["source_id"] = <source row id>``; entities without a
        backing row keep their own id as provenance where the field exists.
        """
        concrete = {field.name for field in model._meta.concrete_fields}
        if "custom_fields" not in concrete:
            return
        raw = values.get("custom_fields")
        if isinstance(raw, dict):
            custom = dict(raw)
        elif isinstance(raw, str):
            try:
                custom = json.loads(raw)
            except (TypeError, ValueError):
                custom = {}
        else:
            custom = {}
        if not isinstance(custom, dict):
            custom = {}
        custom["source_id"] = old_id
        values["custom_fields"] = custom

    @staticmethod
    def _copy_extra_relations(
        *,
        ctx: AuthContext,
        snapshot: dict[str, Any],
        created_rows: list[tuple[str, str, Any]],
        id_map: dict[str, str],
        target: Any,
    ) -> None:
        """Copy relation carriers that have no transfer spec of their own.

        Trace links (including allocation and group membership), comments,
        parent hierarchy and test runs are transfer entities and were already
        imported by the entity loop. The ``test_runs`` relation additionally
        has a join row (TestRunResult) that connects a run to a TestCase; the
        registry keeps that exception declarative instead of adding a per-type
        branch to the entity loop.
        """
        from django.apps import apps

        if not snapshot.get("source_workspace_id"):
            return
        test_run_ids = {
            old_id for key, old_id, _ in created_rows if key == "test_run" and old_id
        }
        if not test_run_ids:
            return
        service = WorkspaceSnapshotService()
        for relation in ARTIFACT_RELATIONS:
            label = _EXTRA_RELATION_MODELS.get(relation)
            if label is None:
                continue
            model = apps.get_model(label)
            for source_row in model.objects.filter(test_run_id__in=test_run_ids):
                row = _serialize_row(source_row)
                values, deferred = service._target_values(
                    model, row, target.id, ctx.tenant_id, id_map, ensure_artifact=False
                )
                # Every reference is mapped by now; a missing TestCase (rare,
                # SET_NULL) simply stays NULL instead of dangling.
                for field_key, old in deferred.items():
                    values[field_key] = id_map.get(old)
                valid_fields = {
                    name
                    for field in model._meta.concrete_fields
                    for name in (field.name, field.attname)
                }
                model.objects.create(
                    **{key: value for key, value in values.items() if key in valid_fields}
                )

    @staticmethod
    def _reconcile_absent_rows(
        *,
        ctx: AuthContext,
        snapshot: dict[str, Any],
        target: Any,
        created_rows: list[tuple[str, str, Any]],
        result: SnapshotImportResult,
    ) -> None:
        """D3b: soft-mark target rows that are absent from the source snapshot.

        Reconciliation never deletes. Each untouched target row keeps its data
        and gains ``not_in_source`` plus the contract's ``status_reconcile``
        value on its backing Artifact (or on the row itself when it has no
        Artifact). The status itself is deliberately advisory — the workflow
        engine still owns the lifecycle state; only the recorded provenance of
        "this row was not in the last snapshot" is written here.
        """
        from persistence.models import Artifact

        touched: dict[str, set[str]] = {}
        for key, _old_id, instance in created_rows:
            touched.setdefault(key, set()).add(str(instance.pk))

        for key, spec in TRANSFER_SPECS.items():
            if not spec.is_artifact or spec.status_reconcile is None:
                continue
            model = _model_for(spec)
            seen = touched.get(key, set())
            try:
                rows = model.objects.filter(**_workspace_filter(model, target.id, ctx))
            except ValidationError:
                continue
            for row in rows:
                if str(row.pk) in seen:
                    continue
                artifact_id = getattr(row, "artifact_id", None)
                artifact = (
                    Artifact.objects.filter(pk=artifact_id).first()
                    if artifact_id is not None
                    else None
                )
                holder = artifact if artifact is not None else row
                if not hasattr(holder, "custom_fields"):
                    continue
                custom = dict(holder.custom_fields or {})
                custom["not_in_source"] = True
                custom["not_in_source_status"] = spec.status_reconcile
                holder.custom_fields = custom
                holder.save(update_fields=["custom_fields"])
                result.reconciled[spec.type_name] = result.reconciled.get(spec.type_name, 0) + 1

    @staticmethod
    def _copy_many_to_many(
        *,
        snapshot: dict[str, Any],
        created_rows: list[tuple[str, str, Any]],
        id_map: dict[str, str],
    ) -> None:
        """Replay M2M join rows generically through the contract id map.

        M2M fields are not concrete columns, so they are not part of the
        serialized entity rows. For a same-tenant snapshot the source row is
        still readable; its M2M targets are copied onto the cloned instance,
        remapped when they name an imported entity. Cross-tenant imports stop
        at the dry-run preview, so this never reads a foreign tenant's rows.
        """
        if not snapshot.get("source_workspace_id"):
            return
        for key, old_id, instance in created_rows:
            if not old_id:
                continue
            spec = spec_for(key)
            if spec is None or not instance._meta.many_to_many:
                continue
            model = _model_for(spec)
            # Tenant-scoped manager: a foreign source row is invisible here.
            source = model.objects.filter(pk=old_id).first()
            if source is None:
                continue
            for field in model._meta.many_to_many:
                related_ids = list(getattr(source, field.name).values_list("pk", flat=True))
                if not related_ids:
                    continue
                new_ids = [
                    UUID(id_map[str(related)]) if str(related) in id_map else related
                    for related in related_ids
                ]
                getattr(instance, field.name).set(new_ids)


__all__ = ["SNAPSHOT_FORMAT_VERSION", "SnapshotImportResult", "WorkspaceSnapshotService"]
