"""R4 / plan §7 — mandatory artifact-transfer test matrix.

Every one of the 25 entries in :data:`TRANSFER_SPECS` is exercised through the
real services: ``WorkspaceSnapshotService.export_snapshot`` followed by
``import_snapshot`` into a new workspace, then a field-by-field and
relation-by-relation comparison. The additional tests cover every target mode
(``target=new``, ``target=existing`` with version-guard, ``conflict -> update``,
``reconcile_status``, ``dry_run``, idempotent replay), the cross-tenant/RLS
gates, checksum refusal and an executable >=100k-row bulk case.

No ORM access is stubbed: the round-trip is performed against the real
pytest-django test database. Only synthetic fixtures are created here — no
production data, PII, secrets or credentials appear in this module.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from django.db import models

from application.artifact_transfer_contract import (
    TRANSFER_SPECS,
    ArtifactTransferSpec,
    artifact_specs,
    spec_for,
)
from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.generic_export_service import _model_for, _serialize_row
from application.workspace_snapshot_service import WorkspaceSnapshotService
from auth_tenancy.context import AuthContext
from application.models import Comment
from persistence.models import Artifact, Milestone, Requirement, Workspace
from persistence.tests.factories import (
    active_tenant,
    ctx_for_user,
    editor_ctx,
    make_requirement,
    make_user,
    make_workspace,
)

ENTITY_KEYS: tuple[str, ...] = tuple(TRANSFER_SPECS)
ARTIFACT_KEYS: tuple[str, ...] = tuple(spec.entity_key for spec in artifact_specs())

#: Scalar columns whose value is an identity/FK target and therefore remapped
#: by the transfer contract (D9/D10/D12b) — excluded from value parity.
REMAP_SCALAR_KEYS: frozenset[str] = frozenset(
    {"workspace_id", "source_element_id", "target_element_id", "lineage_id"}
)

#: Relation carriers copied and remapped by a full snapshot copy (D10).
REMAP_RELATION_NAMES: frozenset[str] = frozenset(
    {
        "artifact", "workspace", "parent", "source",
        "target", "document", "baseline", "target_artifact",
    }
)

#: Auto-maintained columns that legitimately differ after a fresh insert.
VOLATILE_KEYS: frozenset[str] = frozenset({"created_at", "modified_at", "updated_at"})


# ---------------------------------------------------------------------------
# Synthetic-data helpers
# ---------------------------------------------------------------------------


def _synthetic_value(field: models.Field, marker: str) -> object:
    """Return one realistic, deterministic value for a required scalar field."""
    if field.choices:
        return field.choices[0][0]
    if isinstance(field, models.BooleanField):
        return False
    if isinstance(field, models.DateTimeField):
        return datetime(2026, 3, 17, 9, 30, tzinfo=timezone.utc)
    if isinstance(field, models.DateField):
        return date(2026, 3, 17)
    if isinstance(field, models.JSONField):
        return {}
    if isinstance(field, models.UUIDField):
        return uuid.uuid5(uuid.NAMESPACE_URL, f"transfer-matrix:{marker}:{field.name}")
    if isinstance(field, models.DecimalField):
        return Decimal("1")
    if isinstance(field, (models.IntegerField, models.FloatField)):
        return 1
    value = f"{marker}-{field.name}"
    max_length = getattr(field, "max_length", None)
    return value[:max_length] if max_length else value


def _create_source_row(
    model: type[models.Model],
    spec: ArtifactTransferSpec,
    workspace: Workspace,
    marker: str,
    deps: dict[str, object],
) -> models.Model:
    """Create one real source row for *spec* with all required relations set."""
    kwargs: dict[str, object] = {}
    for field in model._meta.concrete_fields:
        name = field.name
        if field.primary_key or field.auto_created:
            continue
        if name in {
            "tenant", "created_at", "created_by", "modified_at", "modified_by", "version"
        }:
            continue
        if getattr(field, "auto_now", False) or getattr(field, "auto_now_add", False):
            continue
        if field.is_relation:
            if name == "workspace":
                kwargs[name] = workspace
            elif name == "artifact":
                kwargs[name] = Artifact.objects.create(
                    workspace=workspace, artifact_type=spec.type_name
                )
            elif name == "document":
                kwargs[name] = deps["document"]
            elif name == "source":
                kwargs[name] = deps["source_artifact"]
            elif name == "target":
                kwargs[name] = deps["target_artifact"]
            elif field.null or field.blank:
                continue
            else:
                kwargs[name] = Artifact.objects.create(
                    workspace=workspace, artifact_type=spec.type_name
                )
            continue
        if name == "workspace_id":
            kwargs[name] = workspace.id
            continue
        if name == "source_element_id":
            kwargs[name] = deps["source_artifact"].id
            continue
        if name == "target_element_id":
            kwargs[name] = deps["target_artifact"].id
            continue
        if field.has_default() or field.null or field.blank:
            continue
        kwargs[name] = _synthetic_value(field, marker)
    return model.objects.create(**kwargs)


def _make_deps(workspace: Workspace, entity_key: str, marker: str) -> dict[str, object]:
    """Build the small cross-entity scaffold a source row may point at."""
    deps: dict[str, object] = {
        "source_artifact": Artifact.objects.create(
            workspace=workspace, artifact_type="ArchitectureElement"
        ),
        "target_artifact": Artifact.objects.create(
            workspace=workspace, artifact_type="ArchitectureElement"
        ),
    }
    if entity_key == "work_item":
        doc_spec = spec_for("document")
        assert doc_spec is not None
        deps["document"] = _create_source_row(
            _model_for(doc_spec), doc_spec, workspace, f"{marker}-dep", deps
        )
    return deps


def _snapshot_row(rows: list[dict], obj: models.Model) -> dict:
    """Locate the exact serialized source row for one created object."""
    match = next((row for row in rows if str(row.get("id")) == str(obj.id)), None)
    assert match is not None, f"No snapshot row for {type(obj).__name__} {obj.id}"
    return match


def _workspace_id_of(obj: models.Model) -> str:
    """Resolve the owning workspace of any related row."""
    workspace_id = getattr(obj, "workspace_id", None)
    if workspace_id is not None:
        return str(workspace_id)
    artifact_id = getattr(obj, "artifact_id", None)
    if artifact_id is not None:
        return str(Artifact.unscoped.get(pk=artifact_id).workspace_id)
    raise AssertionError(f"{type(obj).__name__} {obj.pk} has no workspace scoping")


def _assert_field_parity(
    model: type[models.Model], source_row: dict, target_row: dict
) -> None:
    """Compare every authoritative scalar column of one round-tripped row."""
    compared = 0
    for field in model._meta.concrete_fields:
        name = field.name
        if field.primary_key or field.is_relation or name in VOLATILE_KEYS:
            continue
        if name in REMAP_SCALAR_KEYS or getattr(field, "auto_now", False):
            continue
        if name not in source_row:
            continue
        assert target_row.get(name) == source_row.get(name), (
            f"{model.__name__}.{name}: {source_row.get(name)!r} != {target_row.get(name)!r}"
        )
        compared += 1
    assert compared > 0, f"No comparable scalar fields for {model.__name__}"


def _assert_relation_remap(
    model: type[models.Model],
    source_row: dict,
    target_row: dict,
    target_workspace_id: object,
    ctx: AuthContext,
) -> None:
    """Verify that every non-null relation carrier was rebound to the target."""
    # Some entities (Adr, Risk, Goal, Baseline, …) keep the workspace as a
    # scalar UUID column rather than an FK; still an identity that is remapped.
    source_workspace = source_row.get("workspace_id")
    if source_workspace is not None:
        assert str(target_row.get("workspace_id")) == str(target_workspace_id)
    for field in model._meta.concrete_fields:
        if not field.is_relation:
            continue
        key = f"{field.name}_id"
        old = source_row.get(key)
        new = target_row.get(key)
        if old is None:
            continue
        if field.name == "tenant":
            assert new == str(ctx.tenant_id)
            continue
        if field.name == "workspace":
            assert new == str(target_workspace_id)
            continue
        if field.name not in REMAP_RELATION_NAMES:
            continue
        assert new is not None and str(new) != str(old), (
            f"{model.__name__}.{field.name} kept source id {old}"
        )
        related = field.related_model.objects.get(pk=new)
        assert _workspace_id_of(related) == str(target_workspace_id), (
            f"{model.__name__}.{field.name} points outside the target workspace"
        )
    for key in ("source_element_id", "target_element_id"):
        old = source_row.get(key)
        if old is None:
            continue
        new = target_row.get(key)
        assert new is not None and str(new) != str(old), f"{model.__name__}.{key} not remapped"
        assert _workspace_id_of(Artifact.unscoped.get(pk=new)) == str(target_workspace_id)


# ---------------------------------------------------------------------------
# 1. Parametrized round-trip over all 25 entities (field + relation parity)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("entity_key", ENTITY_KEYS, ids=ENTITY_KEYS)
def test_round_trip_field_and_relation_parity_for_every_entity(entity_key: str) -> None:
    spec = TRANSFER_SPECS[entity_key]
    with active_tenant() as tenant:
        source = make_workspace(tenant)
        ctx = editor_ctx(tenant, source)
        service = WorkspaceSnapshotService()
        snapshot = service.export_snapshot(ctx=ctx, workspace_id=source.id)

        if not spec.is_artifact:
            # D8/D11: configuration entities are metadata, deliberately absent
            # from the per-workspace artifact snapshot and never round-tripped.
            assert spec.roundtrip is False
            assert entity_key not in snapshot["entities"]
            if entity_key == "link_type":
                assert spec.scope == "workspace_config"
            else:
                assert spec.scope == "global_config"
            return

        marker = uuid.uuid4().hex[:12]
        deps = _make_deps(source, entity_key, marker)
        model = _model_for(spec)
        source_obj = _create_source_row(model, spec, source, marker, deps)

        snapshot = service.export_snapshot(ctx=ctx, workspace_id=source.id)
        source_row = _snapshot_row(snapshot["entities"][entity_key], source_obj)

        result = service.import_snapshot(
            ctx=ctx, snapshot=snapshot, new_workspace_name=f"Matrix Copy {marker}"
        )
        assert result.success is True
        assert result.created.get(spec.type_name, 0) >= 1

        new_id = result.id_map.get(str(source_obj.id))
        assert new_id is not None, f"{entity_key}: source id was not remapped"
        target_obj = model.objects.get(pk=new_id)
        target_row = _serialize_row(target_obj)

        _assert_field_parity(model, source_row, target_row)
        _assert_relation_remap(model, source_row, target_row, result.workspace_id, ctx)


@pytest.mark.django_db
def test_snapshot_exposes_exactly_the_artifact_entity_surface() -> None:
    with active_tenant() as tenant:
        source = make_workspace(tenant)
        ctx = editor_ctx(tenant, source)
        snapshot = WorkspaceSnapshotService().export_snapshot(
            ctx=ctx, workspace_id=source.id
        )
        assert set(snapshot["entities"]) == set(ARTIFACT_KEYS)
        assert len(ARTIFACT_KEYS) == 22


# ---------------------------------------------------------------------------
# 2. target=existing with version-guard
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_target_existing_version_guard_skips_unchanged_and_refuses_changed_rows() -> None:
    with active_tenant() as tenant:
        source = make_workspace(tenant)
        target = make_workspace(tenant)
        original = make_requirement(
            source, title="Version Guard Requirement", description="Original body"
        )
        ctx = editor_ctx(tenant, source)
        service = WorkspaceSnapshotService()
        snapshot = service.export_snapshot(ctx=ctx, workspace_id=source.id)

        first = service.import_snapshot(
            ctx=ctx, snapshot=snapshot, target_workspace_id=target.id
        )
        assert first.created.get("Requirement") == 1
        copied = Requirement.objects.get(artifact__workspace_id=target.id)
        assert copied.title == original.title
        assert copied.version == original.version

        second = service.import_snapshot(
            ctx=ctx, snapshot=snapshot, target_workspace_id=target.id
        )
        assert second.skipped.get("Requirement") == 1
        assert Requirement.objects.filter(artifact__workspace_id=target.id).count() == 1

        copied.description = "Locally diverged body"
        copied.version = original.version + 1
        copied.save(update_fields=["description", "version"])

        third = service.import_snapshot(
            ctx=ctx, snapshot=snapshot, target_workspace_id=target.id
        )
        assert third.skipped.get("Requirement") == 1
        assert any("version-guard" in warning for warning in third.warnings)
        copied.refresh_from_db()
        assert copied.description == "Locally diverged body"


# ---------------------------------------------------------------------------
# 3. conflict -> update
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_conflict_mode_update_overwrites_divergent_target_fields() -> None:
    with active_tenant() as tenant:
        source = make_workspace(tenant)
        target = make_workspace(tenant)
        make_requirement(source, title="Update Target Requirement", description="Authoritative")
        ctx = editor_ctx(tenant, source)
        service = WorkspaceSnapshotService()
        snapshot = service.export_snapshot(ctx=ctx, workspace_id=source.id)

        service.import_snapshot(ctx=ctx, snapshot=snapshot, target_workspace_id=target.id)
        copied = Requirement.objects.get(artifact__workspace_id=target.id)
        copied.description = "Locally diverged body"
        copied.save(update_fields=["description"])

        result = service.import_snapshot(
            ctx=ctx,
            snapshot=snapshot,
            target_workspace_id=target.id,
            conflict_mode="update",
        )
        assert result.updated.get("Requirement") == 1
        copied.refresh_from_db()
        assert copied.description == "Authoritative"
        assert Requirement.objects.filter(artifact__workspace_id=target.id).count() == 1


# ---------------------------------------------------------------------------
# 4. reconcile_status: never delete, status map, not_in_source
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_reconcile_status_soft_marks_absent_rows_and_never_deletes() -> None:
    with active_tenant() as tenant:
        source = make_workspace(tenant)
        target = make_workspace(tenant)
        make_requirement(source, title="Snapshot Kept")
        # Distinct uid: this is a genuinely different logical requirement,
        # not a newer version of the source row (D1 upsert key).
        make_requirement(target, title="Only In Target", uid="REQ-ONLY-IN-TARGET")
        ctx = editor_ctx(tenant, source)
        service = WorkspaceSnapshotService()
        snapshot = service.export_snapshot(ctx=ctx, workspace_id=source.id)

        result = service.import_snapshot(
            ctx=ctx,
            snapshot=snapshot,
            target_workspace_id=target.id,
            conflict_mode="reconcile_status",
        )

        gone = Requirement.objects.get(
            artifact__workspace_id=target.id, title="Only In Target"
        )
        custom = dict(gone.artifact.custom_fields or {})
        assert custom.get("not_in_source") is True
        assert (
            custom.get("not_in_source_status")
            == TRANSFER_SPECS["requirement"].status_reconcile
            == "outdated"
        )
        assert result.reconciled.get("Requirement") == 1
        # D3b: the row still exists — reconciliation must never delete.
        assert Requirement.objects.filter(
            artifact__workspace_id=target.id, title="Only In Target"
        ).exists()
        assert Requirement.objects.filter(
            artifact__workspace_id=target.id, title="Snapshot Kept"
        ).exists()


# ---------------------------------------------------------------------------
# 5. dry_run
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_dry_run_preview_counts_without_writing() -> None:
    with active_tenant() as tenant:
        source = make_workspace(tenant)
        make_requirement(source, title="Dry Run Requirement")
        ctx = editor_ctx(tenant, source)
        service = WorkspaceSnapshotService()
        snapshot = service.export_snapshot(ctx=ctx, workspace_id=source.id)

        preview = service.import_snapshot(
            ctx=ctx, snapshot=snapshot, new_workspace_name="Preview Copy", dry_run=True
        )
        assert preview.dry_run is True
        assert preview.created.get("Requirement") == 1
        assert preview.created.get("Artifact") == 1
        assert not Workspace.objects.filter(name="Preview Copy").exists()
        assert Requirement.objects.filter(title="Dry Run Requirement").count() == 1


# ---------------------------------------------------------------------------
# 6. idempotent replay
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_idempotent_replay_does_not_duplicate_rows() -> None:
    with active_tenant() as tenant:
        source = make_workspace(tenant)
        make_requirement(source, title="Replay Requirement")
        ctx = editor_ctx(tenant, source)
        service = WorkspaceSnapshotService()
        snapshot = service.export_snapshot(ctx=ctx, workspace_id=source.id)

        first = service.import_snapshot(
            ctx=ctx, snapshot=snapshot, new_workspace_name="Replay Copy"
        )
        second = service.import_snapshot(
            ctx=ctx, snapshot=snapshot, target_workspace_id=first.workspace_id
        )
        assert second.skipped.get("Requirement") == 1
        assert (
            Requirement.objects.filter(artifact__workspace_id=first.workspace_id).count() == 1
        )


# ---------------------------------------------------------------------------
# 7. cross-tenant gates + RLS
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_cross_tenant_gates_and_row_level_isolation() -> None:
    with active_tenant() as tenant_a:
        source = make_workspace(tenant_a)
        foreign = make_requirement(source, title="Foreign Requirement")
        ctx_a = editor_ctx(tenant_a, source)
        snapshot = WorkspaceSnapshotService().export_snapshot(
            ctx=ctx_a, workspace_id=source.id
        )
    with active_tenant() as tenant_b:
        target = make_workspace(tenant_b)
        editor_b = editor_ctx(tenant_b, target)

        # RLS read gate: an identity of tenant B cannot export tenant A's data.
        with pytest.raises(NotFoundError):
            WorkspaceSnapshotService().export_snapshot(
                ctx=editor_b, workspace_id=source.id
            )

        # Cross-tenant writes are never implicit: editor is refused outright.
        with pytest.raises(PermissionDeniedError):
            WorkspaceSnapshotService().import_snapshot(
                ctx=editor_b, snapshot=snapshot, target_workspace_id=target.id
            )

        admin_b = ctx_for_user(
            tenant_b, make_user(tenant_b), workspace=target, roles=("admin",)
        )
        preview = WorkspaceSnapshotService().import_snapshot(
            ctx=admin_b, snapshot=snapshot, target_workspace_id=target.id, dry_run=True
        )
        assert preview.dry_run is True
        assert preview.created.get("Requirement") == 1
        with pytest.raises(ValidationError, match="dry_run"):
            WorkspaceSnapshotService().import_snapshot(
                ctx=admin_b, snapshot=snapshot, target_workspace_id=target.id
            )

        # An authorized write always stamps the caller's tenant (D12b), never
        # the tenant recorded in the source snapshot.
        authorized = dict(snapshot)
        authorized["source_tenant_id"] = str(tenant_b.id)
        authorized["checksum"] = WorkspaceSnapshotService._checksum(authorized)
        result = WorkspaceSnapshotService().import_snapshot(
            ctx=admin_b, snapshot=authorized, target_workspace_id=target.id
        )
        assert result.success is True
        copied = Requirement.objects.get(artifact__workspace_id=target.id)
        assert copied.tenant_id == tenant_b.id
        assert Requirement.unscoped.get(pk=foreign.id).tenant_id == tenant_a.id


# ---------------------------------------------------------------------------
# 8. checksum mismatch refusal
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_checksum_mismatch_is_refused() -> None:
    with active_tenant() as tenant:
        source = make_workspace(tenant)
        make_requirement(source, title="Checksum Requirement")
        ctx = editor_ctx(tenant, source)
        service = WorkspaceSnapshotService()
        snapshot = service.export_snapshot(ctx=ctx, workspace_id=source.id)

        tampered_row = dict(snapshot)
        tampered_row["entities"] = {
            key: [dict(row) for row in rows]
            for key, rows in snapshot["entities"].items()
        }
        tampered_row["entities"]["requirement"][0]["title"] = "Tampered"
        with pytest.raises(ValidationError, match="checksum"):
            service.import_snapshot(
                ctx=ctx, snapshot=tampered_row, new_workspace_name="Bad Snapshot"
            )

        bad_digest = dict(snapshot)
        bad_digest["checksum"] = "0" * 64
        with pytest.raises(ValidationError, match="checksum"):
            service.import_snapshot(
                ctx=ctx, snapshot=bad_digest, new_workspace_name="Bad Digest"
            )


# ---------------------------------------------------------------------------
# 9. large data (>=100k rows via bulk_create, slow but executable)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.slow
def test_large_snapshot_export_over_one_hundred_thousand_rows() -> None:
    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        ctx = editor_ctx(tenant, workspace)
        rows = [
            Milestone(
                tenant=tenant,
                workspace=workspace,
                name=f"Large Review Milestone {index:06d}",
                review_type=Milestone.ReviewType.PDR,
                target_date=date(2027, 1, 15),
            )
            for index in range(100_005)
        ]
        Milestone.objects.bulk_create(rows, batch_size=5_000)

        snapshot = WorkspaceSnapshotService().export_snapshot(
            ctx=ctx, workspace_id=workspace.id
        )
        assert len(snapshot["entities"]["milestone"]) >= 100_000
        assert snapshot["checksum"]

        preview = WorkspaceSnapshotService().import_snapshot(
            ctx=ctx, snapshot=snapshot, new_workspace_name="Large Copy", dry_run=True
        )
        assert preview.created.get("Milestone") >= 100_000


# ---------------------------------------------------------------------------
# 10. relation carriers (trace/ hierarchy / comments / group / allocation)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_relation_carriers_are_remapped_on_full_copy() -> None:
    from persistence.models import ArchitectureElement, TraceLink

    with active_tenant() as tenant:
        source = make_workspace(tenant)
        ctx = editor_ctx(tenant, source)
        marker = uuid.uuid4().hex[:12]
        deps = _make_deps(source, "trace_link", marker)

        parent = _create_source_row(
            ArchitectureElement,
            TRANSFER_SPECS["architecture_element"],
            source,
            f"{marker}-parent",
            deps,
        )
        child = ArchitectureElement.objects.create(
            tenant=tenant,
            workspace=source,
            artifact=Artifact.objects.create(
                workspace=source, artifact_type="ArchitectureElement"
            ),
            title=f"{marker}-child",
            parent=parent,
        )
        allocation = TraceLink.objects.create(
            tenant=tenant,
            source=deps["source_artifact"],
            target=deps["target_artifact"],
            link_type="allocated-to",
            rationale=f"{marker}-allocation",
        )
        membership = TraceLink.objects.create(
            tenant=tenant,
            source=deps["source_artifact"],
            target=deps["target_artifact"],
            link_type="grouped-in",
            rationale=f"{marker}-membership",
        )
        comment = Comment.objects.create(
            tenant=tenant,
            artifact=deps["source_artifact"],
            text=f"{marker}-comment",
        )

        snapshot = WorkspaceSnapshotService().export_snapshot(
            ctx=ctx, workspace_id=source.id
        )
        result = WorkspaceSnapshotService().import_snapshot(
            ctx=ctx, snapshot=snapshot, new_workspace_name="Relation Copy"
        )
        target_id = result.workspace_id

        copied_child = ArchitectureElement.objects.get(pk=result.id_map[str(child.id)])
        assert copied_child.parent_id != parent.id
        assert copied_child.parent is not None
        assert _workspace_id_of(copied_child.parent) == str(target_id)

        for original in (allocation, membership):
            copied = TraceLink.objects.get(pk=result.id_map[str(original.id)])
            assert copied.source_id != original.source_id
            assert copied.target_id != original.target_id
            assert _workspace_id_of(copied.source) == str(target_id)
            assert _workspace_id_of(copied.target) == str(target_id)

        copied_comment = Comment.objects.get(pk=result.id_map[str(comment.id)])
        assert copied_comment.artifact_id != comment.artifact_id
        assert _workspace_id_of(copied_comment.artifact) == str(target_id)
