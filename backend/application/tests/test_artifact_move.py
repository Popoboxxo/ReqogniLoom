"""P1 Task 1.3: ``ArtifactService.move`` and ordered sibling reads."""
from __future__ import annotations

import threading

import pytest
from django.db import close_old_connections, connection
from django.db.models import F
from django.test.utils import CaptureQueriesContext

from application.artifact_service import ArtifactService
from application.base import ValidationError
from auth_tenancy.context import AuthContext
from persistence.models import (
    ArchitectureElement,
    Artifact,
    Tenant,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext

# ``transaction=True`` so the concurrent-move test's worker connections can see
# the committed fixtures instead of a pytest-django outer transaction.
pytestmark = pytest.mark.django_db(transaction=True)


def _make_tenant(slug: str) -> Tenant:
    return Tenant.objects.create(name=slug, slug=slug)


def _make_workspace(tenant: Tenant, name: str = "ws") -> Workspace:
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant=tenant, name=name)
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def env(db):
    tenant = _make_tenant("move-tenant")
    user = User.objects.create(
        username="move-user", email="move@example.com", tenant=tenant
    )
    workspace = _make_workspace(tenant, "move-ws")
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method="test",
    )
    return tenant, workspace, ctx


def _artifact(
    tenant: Tenant, workspace: Workspace, artifact_type: str = "Requirement", parent=None
) -> Artifact:
    from application.artifact_service import append_sort_key

    parent_id = parent.id if parent is not None else None
    return Artifact.unscoped.create(
        tenant=tenant,
        workspace=workspace,
        artifact_type=artifact_type,
        parent=parent,
        sort_key=append_sort_key(workspace.id, parent_id, artifact_type),
    )


def _ordered_children(parent: Artifact) -> list[Artifact]:
    return list(
        Artifact.unscoped.filter(parent_id=parent.id).order_by(
            F("sort_key").asc(nulls_last=True), "created_at", "id"
        )
    )


class TestMove:
    def test_move_between_siblings_writes_one_row_and_keeps_version(self, env):
        tenant, workspace, ctx = env
        root = _artifact(tenant, workspace)
        a = _artifact(tenant, workspace, parent=root)
        b = _artifact(tenant, workspace, parent=root)
        c = _artifact(tenant, workspace, parent=root)
        version_before = c.version

        service = ArtifactService()
        with CaptureQueriesContext(connection) as captured:
            service.move(
                artifact_id=c.id,
                new_parent_id=root.id,
                after_id=a.id,
                ctx=ctx,
            )

        updates = [
            query["sql"]
            for query in captured.captured_queries
            if query["sql"].lstrip().upper().startswith("UPDATE")
            and "pl_artifact" in query["sql"]
        ]
        assert len(updates) == 1
        assert [row.id for row in _ordered_children(root)] == [a.id, c.id, b.id]
        assert Artifact.unscoped.get(pk=c.id).version == version_before

    def test_move_first_and_last(self, env):
        tenant, workspace, ctx = env
        root = _artifact(tenant, workspace)
        a = _artifact(tenant, workspace, parent=root)
        b = _artifact(tenant, workspace, parent=root)
        c = _artifact(tenant, workspace, parent=root)
        service = ArtifactService()

        service.move(
            artifact_id=c.id, new_parent_id=root.id, after_id=None, ctx=ctx
        )
        assert next(row.id for row in _ordered_children(root)) == c.id

        service.move(artifact_id=a.id, new_parent_id=root.id, ctx=ctx)
        assert [row.id for row in _ordered_children(root)][-1] == a.id
        assert {row.id for row in _ordered_children(root)} == {a.id, b.id, c.id}

    def test_after_id_not_child_is_rejected(self, env):
        tenant, workspace, ctx = env
        root = _artifact(tenant, workspace)
        other_root = _artifact(tenant, workspace)
        _artifact(tenant, workspace, parent=root)
        stranger = _artifact(tenant, workspace, parent=other_root)

        with pytest.raises(ValidationError):
            ArtifactService().move(
                artifact_id=root.id,
                new_parent_id=root.id,
                after_id=stranger.id,
                ctx=ctx,
            )

    def test_move_into_descendant_is_rejected(self, env):
        tenant, workspace, ctx = env
        root = _artifact(tenant, workspace)
        child = _artifact(tenant, workspace, parent=root)

        with pytest.raises(ValidationError):
            ArtifactService().move(
                artifact_id=root.id, new_parent_id=child.id, ctx=ctx
            )

    def test_move_across_workspace_is_rejected(self, env):
        tenant, workspace, ctx = env
        root = _artifact(tenant, workspace)
        other_ws = _make_workspace(tenant, "other-ws")
        foreign = _artifact(tenant, other_ws)

        with pytest.raises(ValidationError):
            ArtifactService().move(
                artifact_id=root.id, new_parent_id=foreign.id, ctx=ctx
            )

    def test_requirement_under_architecture_is_rejected(self, env):
        tenant, workspace, ctx = env
        requirement = _artifact(tenant, workspace)
        element = _artifact(tenant, workspace, artifact_type="ArchitectureElement")

        with pytest.raises(ValidationError):
            ArtifactService().move(
                artifact_id=requirement.id, new_parent_id=element.id, ctx=ctx
            )

    def test_architecture_invariants_I1_I5(self, env):
        tenant, workspace, ctx = env
        root_artifact = _artifact(
            tenant, workspace, artifact_type="ArchitectureElement"
        )
        root_element = ArchitectureElement.unscoped.create(
            tenant=tenant,
            artifact=root_artifact,
            workspace=workspace,
            title="System",
        )
        child_artifact = _artifact(
            tenant, workspace, artifact_type="ArchitectureElement", parent=root_artifact
        )
        child_element = ArchitectureElement.unscoped.create(
            tenant=tenant,
            artifact=child_artifact,
            workspace=workspace,
            title="Sub",
            parent=root_element,
        )
        # A legacy second root, written directly to set up the I5 case.
        second_root_artifact = _artifact(
            tenant, workspace, artifact_type="ArchitectureElement"
        )
        ArchitectureElement.unscoped.create(
            tenant=tenant,
            artifact=second_root_artifact,
            workspace=workspace,
            title="Second",
        )

        service = ArtifactService()
        with pytest.raises(ValidationError):
            service.move(
                artifact_id=root_artifact.id,
                new_parent_id=child_artifact.id,
                ctx=ctx,
            )
        with pytest.raises(ValidationError):
            service.move(
                artifact_id=second_root_artifact.id,
                new_parent_id=None,
                ctx=ctx,
            )
        assert ArchitectureElement.unscoped.get(pk=child_element.pk).parent_id is not None

    def test_audit_event_reordered(self, env):
        from unittest.mock import patch

        tenant, workspace, ctx = env
        root = _artifact(tenant, workspace)
        a = _artifact(tenant, workspace, parent=root)
        b = _artifact(tenant, workspace, parent=root)

        with patch.object(ArtifactService, "_audit") as audit:
            ArtifactService().move(
                artifact_id=b.id, new_parent_id=root.id, after_id=a.id, ctx=ctx
            )

        assert audit.call_args.kwargs["operation"] == "reordered"

    def test_lists_and_tree_follow_sort_key(self, env):
        tenant, workspace, ctx = env
        service = ArtifactService()
        root_artifact = _artifact(tenant, workspace)
        a = _artifact(tenant, workspace, parent=root_artifact)
        _artifact(tenant, workspace, parent=root_artifact)
        _artifact(tenant, workspace, parent=root_artifact)

        service.move(
            artifact_id=a.id, new_parent_id=root_artifact.id, ctx=ctx
        )

        tree = service.get_tree(
            root_id=root_artifact.id, workspace_id=workspace.id, ctx=ctx
        )
        assert [child.id for child in tree.children][-1] == a.id
        assert all(child.sort_key for child in tree.children)

    def test_new_child_appended_last(self, env):
        tenant, workspace, _ctx = env
        root = _artifact(tenant, workspace)
        first = _artifact(tenant, workspace, parent=root)
        _artifact(tenant, workspace, parent=root)
        last = _artifact(tenant, workspace, parent=root)

        order = [row.id for row in _ordered_children(root)]
        assert order[0] == first.id
        assert order[-1] == last.id

    def test_concurrent_moves_same_parent_keep_keys_unique(self, env):
        tenant, workspace, ctx = env
        root = _artifact(tenant, workspace)
        siblings = [_artifact(tenant, workspace, parent=root) for _ in range(4)]
        barrier = threading.Barrier(2)
        errors: list[BaseException] = []

        def _move(artifact_id, after_id):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                ArtifactService().move(
                    artifact_id=artifact_id,
                    new_parent_id=root.id,
                    after_id=after_id,
                    ctx=ctx,
                )
            except BaseException as exc:  # noqa: BLE001 - surfaced below
                errors.append(exc)
            finally:
                close_old_connections()

        threads = [
            threading.Thread(target=_move, args=(siblings[2].id, siblings[0].id)),
            threading.Thread(target=_move, args=(siblings[3].id, siblings[1].id)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert not errors
        rows = _ordered_children(root)
        keys = [row.sort_key for row in rows]
        assert len(keys) == len(set(keys))
        assert keys == sorted(keys)
