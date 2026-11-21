"""R2/P6: ``clone_workspace`` must copy every entity and every relation.

The old clone handled six entity types by hand. P6 delegates the copy to the
snapshot import, which is contract-driven, so this test pins both sides:

* all 22 artifact-scoped contract entities survive with new ids,
* all six relation carriers (trace links, parent hierarchy, allocation,
  group membership, comments, test runs) survive with remapped endpoints,
* ``source_id`` provenance is stamped on the cloned backing artifacts,
* a dry run writes nothing and cross-tenant imports fail closed.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from django.db import models
from django.utils import timezone

from application.artifact_transfer_contract import TRANSFER_SPECS, artifact_specs
from application.base import PermissionDeniedError, ValidationError
from application.generic_export_service import _model_for, _workspace_filter
from application.models import Comment
from application.workspace_service import WorkspaceService
from application.workspace_snapshot_service import WorkspaceSnapshotService
from persistence.models import (
    Artifact,
    ArchitectureElement,
    Requirement,
    TestCase,
    TestRunResult,
    TraceLink,
    Workspace,
)
from persistence.tests.factories import (
    active_tenant,
    ctx_for_user,
    editor_ctx,
    make_user,
    make_workspace,
)


def _scalar(field: models.Field) -> object:
    """A deterministic, DB-valid value for a required scalar field."""
    choices = getattr(field, "choices", None)
    if choices:
        return choices[0][0]
    if isinstance(field, models.BooleanField):
        return False
    if isinstance(field, models.DateTimeField):
        return timezone.now()
    if isinstance(field, models.DateField):
        return timezone.now().date()
    if isinstance(field, models.UUIDField):
        return uuid4()
    if isinstance(field, models.IntegerField):
        return 1
    if isinstance(field, (models.FloatField, models.DecimalField)):
        return 1.0
    if isinstance(field, models.JSONField):
        return {}
    if isinstance(field, (models.CharField, models.TextField)):
        value = f"P6-{field.name}"
        return value[: field.max_length] if field.max_length else value
    return "P6"


def _backing(workspace, tenant, artifact_type: str) -> Artifact:
    return Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type=artifact_type
    )


def _make_spec_row(spec, workspace, tenant, *, extras=None):
    """Create one row of a transfer entity plus its backing Artifact.

    Required scalar fields are filled generically by field type; the few
    required relations (WorkItem.document, TraceLink endpoints) are supplied by
    the caller via ``extras``. No production code grows a per-type branch.
    """
    model = _model_for(spec)
    concrete_names = {field.name for field in model._meta.concrete_fields}
    artifact = _backing(workspace, tenant, spec.type_name)
    kwargs: dict[str, object] = {"tenant_id": tenant.id}

    for field in model._meta.concrete_fields:
        name = field.name
        if name in {"id", "tenant", "artifact", "workspace", "workspace_id", "parent"}:
            continue
        if field.primary_key or getattr(field, "auto_now", False) or getattr(field, "auto_now_add", False):
            continue
        if field.is_relation:
            continue
        if field.has_default() or field.blank or field.null:
            continue
        kwargs[name] = _scalar(field)

    if "workspace" in concrete_names:
        kwargs["workspace"] = workspace
    elif "workspace_id" in concrete_names:
        kwargs["workspace_id"] = workspace.id
    if "artifact" in concrete_names:
        kwargs["artifact"] = artifact
    kwargs.update(extras or {})
    return model.objects.create(**kwargs), artifact


def _seed_all_entities(workspace, tenant):
    """Create one row per contract entity and return ``{key: (row, artifact)}``."""
    created: dict[str, tuple] = {}
    uids = {
        "requirement": "P6-REQ-1",
        "test_case": "P6-TC-1",
        "architecture_element": "P6-ARCH-1",
    }
    for spec in artifact_specs():
        extras = {"uid": uids[spec.entity_key]} if spec.entity_key in uids else {}
        if spec.entity_key == "document":
            # WorkItem's mandatory document FK is wired up below.
            pass
        if spec.entity_key == "work_item":
            extras["document"] = created["document"][0]
        if spec.entity_key == "trace_link":
            extras = {
                "source": created["requirement"][1],
                "target": created["test_case"][1],
                "link_type": "derives-from",
            }
        created[spec.entity_key] = _make_spec_row(
            spec, workspace, tenant, extras=extras
        )
    return created


def _seed_relations(workspace, tenant, created):
    """Add the relation carriers not already covered by one row per entity."""
    req_artifact = created["requirement"][1]
    arch_artifact = created["architecture_element"][1]

    # parent_hierarchy — both the generic Artifact tree and the specialised
    # ArchitectureElement tree.
    req_artifact.parent = created["stakeholder_need"][1]
    req_artifact.save(update_fields=["parent"])
    arch_root = created["architecture_element"][0]
    arch_child_artifact = _backing(workspace, tenant, "ArchitectureElement")
    arch_child = ArchitectureElement.objects.create(
        tenant=tenant,
        artifact=arch_child_artifact,
        workspace=workspace,
        title="P6 child",
        uid="P6-ARCH-2",
        parent=arch_root,
    )

    # trace_links / allocation / group_membership — one edge per link type.
    for link_type in ("derives-from", "allocated-to", "grouped-in"):
        TraceLink.objects.create(
            tenant=tenant,
            source=req_artifact,
            target=arch_artifact,
            link_type=link_type,
        )

    # comments — a second comment attached to the requirement artifact.
    Comment.objects.create(tenant=tenant, artifact=req_artifact, text="P6 comment")

    # test_runs — the join row linking a run to a TestCase.
    test_run = created["test_run"][0]
    TestRunResult.objects.create(
        tenant=tenant,
        test_run=test_run,
        test_case=created["test_case"][0],
        status="passed",
        test_case_title="P6 result",
    )
    return arch_child


@pytest.mark.django_db
def test_clone_copies_all_entities_and_all_relations() -> None:
    with active_tenant() as tenant:
        source = make_workspace(tenant)
        created = _seed_all_entities(source, tenant)
        _seed_relations(source, tenant, created)
        ctx = editor_ctx(tenant, source)
        service = WorkspaceService()

        target = service.clone_workspace(ctx, source.id, "P6 Clone")

        # (1) Every contract entity: the source and the clone have identical
        # row counts. The Artifact count also catches duplicate backing rows.
        for key, spec in TRANSFER_SPECS.items():
            if not spec.is_artifact:
                continue  # Workspace/WorkspaceLinkType are config, not data
            model = _model_for(spec)
            src_count = model.objects.filter(
                **_workspace_filter(model, source.id, ctx)
            ).count()
            tgt_count = model.objects.filter(
                **_workspace_filter(model, target.id, ctx)
            ).count()
            assert src_count > 0 and tgt_count == src_count, (
                f"{key}: {src_count} -> {tgt_count}"
            )

        # The extra ArchitectureElement and the extra Artifact hierarchy rows.
        assert Artifact.objects.filter(workspace=target).count() == (
            Artifact.objects.filter(workspace=source).count()
        )
        assert ArchitectureElement.objects.filter(
            artifact__workspace=target
        ).count() == 2

        # (2) No UID collisions: same uids, distinct ids/artifacts in the clone.
        for key in ("requirement", "test_case", "architecture_element"):
            original = created[key][0]
            copied = _model_for(TRANSFER_SPECS[key]).objects.get(
                workspace=target, uid=original.uid
            )
            assert copied.id != original.id
            assert copied.artifact_id != original.artifact_id
            assert copied.artifact_id != created[key][1].id

        # (3) source_id provenance on the cloned backing artifacts.
        cloned_req = Requirement.objects.get(workspace=target, uid="P6-REQ-1")
        assert (
            cloned_req.artifact.custom_fields["source_id"]
            == str(created["requirement"][1].id)
        )

        # (4) Every relation carrier survives with TARGET-side endpoints.
        target_artifact_ids = set(
            Artifact.objects.filter(workspace=target).values_list("id", flat=True)
        )
        links = list(TraceLink.objects.filter(source__workspace=target))
        assert {link.link_type for link in links} >= {
            "derives-from",
            "allocated-to",
            "grouped-in",
        }
        assert all(
            str(link.source_id) in {str(value) for value in target_artifact_ids}
            and str(link.target_id) in {str(value) for value in target_artifact_ids}
            for link in links
        )

        # parent_hierarchy on both the Artifact and the ArchitectureElement tree.
        cloned_arch_child = ArchitectureElement.objects.get(
            workspace=target, uid="P6-ARCH-2"
        )
        assert cloned_arch_child.parent_id is not None
        assert cloned_arch_child.parent_id != created["architecture_element"][0].id
        assert ArchitectureElement.objects.filter(
            artifact__workspace=target, id=cloned_arch_child.parent_id
        ).exists()
        cloned_artifact_with_parent = Artifact.objects.filter(
            workspace=target, parent__isnull=False
        ).first()
        assert cloned_artifact_with_parent is not None
        assert str(cloned_artifact_with_parent.parent_id) in {
            str(value) for value in target_artifact_ids
        }

        # comments and test runs (including the TestRunResult join row).
        assert Comment.objects.filter(artifact__workspace=target).count() == (
            Comment.objects.filter(artifact__workspace=source).count()
        )
        assert all(
            str(comment.artifact_id) in {str(value) for value in target_artifact_ids}
            for comment in Comment.objects.filter(artifact__workspace=target)
        )
        assert TestRunResult.objects.filter(test_run__workspace=target).count() == 1
        cloned_case_ids = set(
            TestCase.objects.filter(workspace=target).values_list("id", flat=True)
        )
        assert TestRunResult.objects.get(
            test_run__workspace=target
        ).test_case_id in cloned_case_ids

        # The source workspace was not mutated by the clone.
        assert Requirement.objects.filter(workspace=source).count() == 1
        assert TraceLink.objects.filter(source__workspace=source).count() >= 3


@pytest.mark.django_db
def test_dry_run_writes_nothing() -> None:
    with active_tenant() as tenant:
        source = make_workspace(tenant)
        created = _seed_all_entities(source, tenant)
        ctx = editor_ctx(tenant, source)
        snapshot = WorkspaceSnapshotService().export_snapshot(
            ctx=ctx, workspace_id=source.id
        )
        before = Requirement.objects.filter(workspace=source).count()

        result = WorkspaceSnapshotService().import_snapshot(
            ctx=ctx,
            snapshot=snapshot,
            new_workspace_name="P6 Would-Be Copy",
            dry_run=True,
        )

        assert result.dry_run is True
        assert result.created.get("Requirement") == 1
        assert not Workspace.objects.filter(name="P6 Would-Be Copy").exists()
        assert Requirement.objects.filter(workspace=source).count() == before
        assert created["requirement"][0].id == Requirement.objects.get(
            workspace=source
        ).id


@pytest.mark.django_db
def test_cross_tenant_import_fails_closed() -> None:
    with active_tenant() as tenant_a:
        source = make_workspace(tenant_a)
        make_requirement_row = _make_spec_row(
            TRANSFER_SPECS["requirement"], source, tenant_a
        )
        ctx_a = editor_ctx(tenant_a, source)
        snapshot = WorkspaceSnapshotService().export_snapshot(
            ctx=ctx_a, workspace_id=source.id
        )
        assert make_requirement_row[0] is not None

    with active_tenant() as tenant_b:
        editor_b = editor_ctx(tenant_b)
        with pytest.raises(PermissionDeniedError, match="admin"):
            WorkspaceSnapshotService().import_snapshot(
                ctx=editor_b,
                snapshot=snapshot,
                new_workspace_name="P6 Cross Tenant",
                dry_run=True,
            )

        admin_b = ctx_for_user(tenant_b, make_user(tenant_b), roles=("admin",))
        with pytest.raises(ValidationError, match="dry_run"):
            WorkspaceSnapshotService().import_snapshot(
                ctx=admin_b,
                snapshot=snapshot,
                new_workspace_name="P6 Cross Tenant",
            )

        preview = WorkspaceSnapshotService().import_snapshot(
            ctx=admin_b,
            snapshot=snapshot,
            new_workspace_name="P6 Cross Tenant",
            dry_run=True,
        )
        assert preview.dry_run is True
        assert not Workspace.objects.filter(name="P6 Cross Tenant").exists()
