"""Plan F F3-T4 — ``WorkItemService``: resume, checkpoints, heartbeat, locking.

The suite runs against a real database and workspaces provisioned with the
tier-matched ``work_item_<tier>`` lifecycle (F3-T2), so the service is exercised
on the same state machines the product uses:

* ``work_item_standard`` — ``todo -> in_progress -> done`` plus ``blocked``;
* ``work_item_extended`` — adds ``in_review`` and makes ``in_review -> done``
  an ``approver``-only edge that records ``approved_by``/``approved_at``.

Covered contracts (docs/superpowers/specs/Archive/2026-11-02-f3-workitem-design.md §4,
§6, §9; plan F §WP F3):

* ``document`` is mandatory and must belong to the item's workspace;
* ``blocked`` needs a non-empty ``blocked_reason`` (rule 10);
* every write action stamps ``last_activity_at``/``last_actor`` (heartbeat A-3);
* ``resume`` returns the newest checkpoint and all non-done/dropped items,
  sorted ``(ordinal, id)`` (G2.1);
* ``expected_version`` answers ``OptimisticLockError`` on a stale value;
* soft delete is the ``Artifact.lifecycle_status`` flag (G1.5), restore clears
  it;
* a foreign tenant cannot read, update or resume the item.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta

import pytest

from application.base import (
    NotFoundError,
    OptimisticLockError,
    PermissionDeniedError,
    ValidationError,
)
from application.work_item_service import WorkItemService
from auth_tenancy.context import AuthContext
from persistence.models import Artifact, Document, Tenant, User, WorkItem, Workspace
from persistence.tenancy import TenantContext
from workflow.item_types import work_item_preset_key
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@contextmanager
def _tenant_scope(tenant_id):
    """Activate a tenant around calls that bypass the service."""
    TenantContext.set_tenant(tenant_id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="Work Item Tenant", slug="work-item-tenant")


@pytest.fixture
def other_tenant():
    return Tenant.objects.create(name="Other WI Tenant", slug="other-wi-tenant")


def _make_workspace(tenant: Tenant, name: str, tier: str = "standard") -> Workspace:
    with _tenant_scope(tenant.id):
        workspace = Workspace.objects.create(
            tenant=tenant, name=name, preset={"name": tier}
        )
        create_default_workflow(
            workspace_id=workspace.id,
            preset=work_item_preset_key(tier),
            item_type="WorkItem",
            tenant_id=tenant.id,
        )
        return workspace


def _document(tenant: Tenant, workspace: Workspace, title: str = "Plan") -> Document:
    with _tenant_scope(tenant.id):
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Document"
        )
        return Document.objects.create(
            tenant=tenant,
            artifact=artifact,
            workspace=workspace,
            title=title,
            kind=Document.Kind.PLAN,
            body="# Plan\n\nWork state.",
        )


def _user(tenant: Tenant, username: str) -> User:
    return User.objects.create(
        username=username, email=f"{username}@example.com", tenant=tenant
    )


def _context(user: User, *roles: str) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant_id,
        active_roles=tuple(roles),
        auth_method="test",
        tenant_name=user.tenant.name,
    )


@pytest.fixture
def editor_ctx(tenant):
    return _context(_user(tenant, "wi-editor"), "editor")


@pytest.fixture
def approver_ctx(tenant):
    return _context(_user(tenant, "wi-approver"), "approver", "editor")


@pytest.fixture
def other_ctx(other_tenant):
    return _context(_user(other_tenant, "other-editor"), "editor")


@pytest.fixture
def workspace(tenant):
    return _make_workspace(tenant, "WI Standard Workspace", tier="standard")


@pytest.fixture
def extended_workspace(tenant):
    return _make_workspace(tenant, "WI Extended Workspace", tier="extended")


@pytest.fixture
def document(tenant, workspace):
    return _document(tenant, workspace)


@pytest.fixture
def service() -> WorkItemService:
    return WorkItemService()


def _create(service: WorkItemService, workspace, document, ctx, **overrides) -> WorkItem:
    payload = {
        "kind": WorkItem.Kind.STEP,
        "title": "Write the work item",
        "body": "## Step\n\nDo the work.",
    }
    payload.update(overrides)
    return service.create_work_item(
        workspace.id, document.id, ctx, **payload
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_create_assigns_uid_workspace_artifact_and_heartbeat(
    service, workspace, document, editor_ctx
):
    item = _create(service, workspace, document, editor_ctx, actor="agent:setup")

    assert item.uid == "WI-001"
    assert item.workspace_id == workspace.id
    assert item.document_id == document.id
    assert item.version == 1
    assert item.last_actor == "agent:setup"
    assert item.last_activity_at is not None
    # The backing Artifact is what makes the item a trace-link endpoint.
    assert item.artifact.artifact_type == "WorkItem"
    assert item.artifact.workspace_id == workspace.id
    assert service.current_status(item.id, editor_ctx) == "todo"


def test_create_requires_a_document(service, workspace, editor_ctx):
    with pytest.raises(ValidationError, match="document"):
        service.create_work_item(
            workspace.id, None, editor_ctx, kind=WorkItem.Kind.STEP, title="Orphan"
        )


def test_create_rejects_a_document_from_another_workspace(
    service, tenant, workspace, editor_ctx
):
    other_workspace = _make_workspace(tenant, "WI Other Workspace", tier="standard")
    foreign_document = _document(tenant, other_workspace)

    with pytest.raises(ValidationError, match="same workspace"):
        service.create_work_item(
            workspace.id,
            foreign_document.id,
            editor_ctx,
            kind=WorkItem.Kind.STEP,
            title="Wrong home",
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"title": "   "}, "title"),
        ({"kind": "Nonsense"}, "kind"),
        ({"progress": 101}, "progress"),
        ({"progress": -1}, "progress"),
        ({"ordinal": -1}, "ordinal"),
        ({"body": "<script>alert(1)</script>"}, "body"),
    ],
)
def test_create_rejects_invalid_input(
    service, workspace, document, editor_ctx, overrides, message
):
    with pytest.raises(ValidationError) as exc:
        _create(service, workspace, document, editor_ctx, **overrides)

    assert message in str(exc.value)


# ---------------------------------------------------------------------------
# Update / progress / optimistic lock
# ---------------------------------------------------------------------------


def test_update_changes_fields_bumps_version_and_heartbeat(
    service, workspace, document, editor_ctx
):
    item = _create(service, workspace, document, editor_ctx)
    old_activity = item.last_activity_at - timedelta(hours=3)
    WorkItem.objects.filter(pk=item.id).update(last_activity_at=old_activity)

    updated = service.update_work_item(
        item.id,
        editor_ctx,
        title="Renamed",
        body="New body",
        next_action="continue here",
        change_reason="clarified",
        actor="agent:update",
    )

    assert updated.title == "Renamed"
    assert updated.body == "New body"
    assert updated.next_action == "continue here"
    assert updated.version == 2
    assert updated.last_actor == "agent:update"
    assert updated.last_activity_at > old_activity


def test_update_rejects_a_stale_expected_version(
    service, workspace, document, editor_ctx
):
    item = _create(service, workspace, document, editor_ctx)
    service.update_work_item(item.id, editor_ctx, title="First edit")

    with pytest.raises(OptimisticLockError):
        service.update_work_item(
            item.id, editor_ctx, title="Second edit", expected_version=1
        )


def test_update_refuses_to_clear_a_blocked_items_reason(
    service, workspace, document, editor_ctx
):
    item = _create(service, workspace, document, editor_ctx)
    service.transition(item.id, "in_progress", editor_ctx)
    service.transition(
        item.id, "blocked", editor_ctx, blocked_reason="waiting on API"
    )

    with pytest.raises(ValidationError, match="blocked_reason"):
        service.update_work_item(item.id, editor_ctx, blocked_reason="   ")


def test_set_progress_validates_and_updates(service, workspace, document, editor_ctx):
    item = _create(service, workspace, document, editor_ctx)

    updated = service.set_progress(item.id, 40, editor_ctx, actor="agent:progress")

    assert updated.progress == 40
    assert updated.version == 2
    assert updated.last_actor == "agent:progress"

    for invalid in (-1, 101):
        with pytest.raises(ValidationError, match="progress"):
            service.set_progress(item.id, invalid, editor_ctx)


# ---------------------------------------------------------------------------
# Transitions — blocked (rule 10) and extended approval
# ---------------------------------------------------------------------------


def test_blocked_transition_requires_a_reason(
    service, workspace, document, editor_ctx
):
    item = _create(service, workspace, document, editor_ctx)
    service.transition(item.id, "in_progress", editor_ctx)

    with pytest.raises(ValidationError, match="blocked_reason"):
        service.transition(item.id, "blocked", editor_ctx)

    blocked = service.transition(
        item.id, "blocked", editor_ctx, blocked_reason="waiting on API"
    )
    assert blocked.blocked_reason == "waiting on API"
    assert service.current_status(item.id, editor_ctx) == "blocked"


def test_extended_done_requires_an_approver_and_records_approval(
    service, tenant, extended_workspace, editor_ctx, approver_ctx
):
    document = _document(tenant, extended_workspace)
    item = _create(service, extended_workspace, document, editor_ctx)

    # The extended preset mandates a change_reason on every transition.
    service.transition(item.id, "in_progress", editor_ctx, change_reason="start")
    service.transition(item.id, "in_review", editor_ctx, change_reason="ready")

    with pytest.raises(PermissionDeniedError, match="approver"):
        service.transition(item.id, "done", editor_ctx, change_reason="sign off")

    done = service.transition(item.id, "done", approver_ctx, change_reason="signed off")

    assert service.current_status(item.id, approver_ctx) == "done"
    assert done.approved_at is not None
    assert done.approved_by
    assert done.approved_by == str(approver_ctx.user_id)


# ---------------------------------------------------------------------------
# Checkpoint / resume
# ---------------------------------------------------------------------------


def test_checkpoint_requires_a_next_action(service, workspace, document, editor_ctx):
    with pytest.raises(ValidationError, match="next_action"):
        service.checkpoint(
            workspace.id, document.id, editor_ctx, next_action="   "
        )


def test_resume_returns_the_newest_checkpoint_and_open_items_sorted(
    service, workspace, document, editor_ctx
):
    late = _create(service, workspace, document, editor_ctx, title="Late", ordinal=2)
    first = _create(service, workspace, document, editor_ctx, title="First", ordinal=0)
    second = _create(service, workspace, document, editor_ctx, title="Second", ordinal=0)
    done_item = _create(
        service, workspace, document, editor_ctx, title="Done", ordinal=1
    )
    service.transition(done_item.id, "in_progress", editor_ctx)
    service.transition(done_item.id, "done", editor_ctx)

    checkpoint_one = service.checkpoint(
        workspace.id, document.id, editor_ctx, next_action="continue with First"
    )
    checkpoint_two = service.checkpoint(
        workspace.id, document.id, editor_ctx, next_action="continue with Second"
    )

    result = service.resume(workspace.id, document.id, editor_ctx)
    open_items = result["open_items"]

    assert result["checkpoint"]["id"] == str(checkpoint_two.id)
    assert result["checkpoint"]["kind"] == WorkItem.Kind.CHECKPOINT
    assert result["checkpoint"]["next_action"] == "continue with Second"

    expected = sorted(
        [late, first, second, checkpoint_one, checkpoint_two],
        key=lambda item: (item.ordinal, item.id),
    )
    assert [entry["id"] for entry in open_items] == [str(item.id) for item in expected]
    assert str(done_item.id) not in {entry["id"] for entry in open_items}
    for entry in open_items:
        assert entry["status"] not in {"done", "dropped"}
        assert isinstance(entry["links"], list)
        assert entry["last_activity_at"] is not None


def test_resume_requires_a_document(service, workspace, editor_ctx):
    with pytest.raises(ValidationError, match="document"):
        service.resume(workspace.id, None, editor_ctx)


def test_resume_rejects_a_foreign_document(
    service, tenant, workspace, editor_ctx, other_tenant
):
    other_workspace = _make_workspace(other_tenant, "Foreign WS", tier="standard")
    foreign_document = _document(other_tenant, other_workspace)

    with pytest.raises(NotFoundError):
        service.resume(workspace.id, foreign_document.id, editor_ctx)


# ---------------------------------------------------------------------------
# Soft delete / restore (G1.5) and tenant isolation
# ---------------------------------------------------------------------------


def test_soft_delete_hides_the_item_and_restore_brings_it_back(
    service, workspace, document, editor_ctx
):
    item = _create(service, workspace, document, editor_ctx)

    service.delete_work_item(item.id, editor_ctx, change_reason="obsolete")

    status = (
        Artifact.objects.filter(pk=item.artifact_id)
        .values_list("lifecycle_status", flat=True)
        .first()
    )
    assert status == "outdated"
    assert service.list_work_items(workspace.id, editor_ctx) == []
    assert service.resume(workspace.id, document.id, editor_ctx)["open_items"] == []
    # V3: still readable, only flagged (the row and its history are intact).
    assert service.get_work_item(item.id, editor_ctx).id == item.id

    service.restore_work_item(item.id, editor_ctx)
    assert [
        entry.id for entry in service.list_work_items(workspace.id, editor_ctx)
    ] == [item.id]
    assert (
        service.resume(workspace.id, document.id, editor_ctx)["open_items"][0]["id"]
        == str(item.id)
    )


def test_restore_of_a_live_item_is_refused(
    service, workspace, document, editor_ctx
):
    item = _create(service, workspace, document, editor_ctx)

    with pytest.raises(ValidationError, match="cannot be restored"):
        service.restore_work_item(item.id, editor_ctx)


def test_foreign_tenant_cannot_read_write_or_resume(
    service, workspace, document, editor_ctx, other_ctx
):
    item = _create(service, workspace, document, editor_ctx)

    with pytest.raises(NotFoundError):
        service.get_work_item(item.id, other_ctx)
    with pytest.raises(NotFoundError):
        service.update_work_item(item.id, other_ctx, title="Hijacked")
    with pytest.raises(NotFoundError):
        service.transition(item.id, "in_progress", other_ctx)
    with pytest.raises(NotFoundError):
        service.delete_work_item(item.id, other_ctx)
    with pytest.raises(NotFoundError):
        service.resume(workspace.id, document.id, other_ctx)
