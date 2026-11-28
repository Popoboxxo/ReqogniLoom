"""DB-backed tests for the diff-based affected-item set of a ChangeRequest.

leaf_id : COMP-AS-021
req_id  : REQ-157, REQ-216

Spec 2026-11-28 §4.2.2 / review finding B5. ``set_affected_items`` used to
delete every impact row and recreate it, destroying the provenance recorded on
the surviving rows (``origin``, ``rationale``, ``state_before``,
``version_before``, ``removed_reason``, ``change_action``). It now reconciles:

    * an id that stays keeps its row — same pk, untouched fields;
    * a new id creates a row with a fresh before-snapshot;
    * a vanished id deletes only its own row;
    * exactly one version bump and one ``ChangeRequestUpdated`` event per call.

Also covers ``update_affected_item`` (PATCH semantics + remove gate) and the
"remove" branch of ``_capture_affected_items_after``.
"""
from __future__ import annotations

import uuid

import pytest

from application.base import NotFoundError, ValidationError
from application.change_request_service import ChangeRequestService
from application.models import ChangeRequest, ChangeRequestAffectedItem, DomainEventOutbox
from auth_tenancy.context import AuthContext
from persistence.models import Artifact, Requirement, Tenant, User, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures (same shape as test_change_request_cm_traceability.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="diff-tenant", slug="diff-tenant")


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username="diff-user", email="diff@example.com", tenant=tenant
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name="ws-diff", preset={"name": "standard"}
        )
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def ctx(user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="diff-tenant",
    )


@pytest.fixture(autouse=True)
def _clear_preset_cache():
    yield
    from presets import gate

    from application.preset_policy_service import get_preset_policy_service

    with gate._cache_lock:
        gate._tier_cache.clear()
    get_preset_policy_service()._cache.clear()


def _requirement_artifact(tenant: Tenant, workspace: Workspace, title: str) -> Artifact:
    TenantContext.set_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="requirement"
        )
        Requirement.objects.create(tenant=tenant, artifact=artifact, title=title)
        return artifact
    finally:
        TenantContext.clear_tenant()


def _cr_with(svc, tenant, workspace, ctx, artifacts) -> ChangeRequest:
    return svc.create_change_request(
        workspace_id=workspace.id,
        title="Diff change set",
        ctx=ctx,
        affected_item_ids=[a.id for a in artifacts],
    )


def _row(cr_id, item_id) -> ChangeRequestAffectedItem | None:
    return ChangeRequestAffectedItem.objects.filter(
        change_request_id=cr_id, item_id=str(item_id)
    ).first()


# ---------------------------------------------------------------------------
# A) diff-based set_affected_items
# ---------------------------------------------------------------------------


class TestSetAffectedItemsIsDiffBased:
    def test_reset_keeps_the_same_row_and_its_provenance(
        self, tenant, workspace, ctx
    ):
        artifact = _requirement_artifact(tenant, workspace, "Kept requirement")
        svc = ChangeRequestService()
        cr = _cr_with(svc, tenant, workspace, ctx, [artifact])

        original = _row(cr.id, artifact.id)
        assert original is not None
        # Simulate an adopted analysis finding with a human rationale.
        updated = svc.update_affected_item(
            cr.id,
            artifact.id,
            ctx,
            origin="analysis",
            rationale="reachable via verifies chain",
        )
        updated.refresh_from_db()
        before_pk = updated.pk
        before_state = updated.state_before
        before_version = updated.version_before
        assert before_state is not None and before_version is not None

        svc.set_affected_items(cr_id=cr.id, item_ids=[artifact.id], ctx=ctx)

        row = _row(cr.id, artifact.id)
        assert row is not None
        assert row.pk == before_pk, "re-set must keep the same row, not recreate it"
        assert row.state_before == before_state
        assert row.version_before == before_version
        assert row.origin == "analysis"
        assert row.rationale == "reachable via verifies chain"
        assert ChangeRequestAffectedItem.objects.filter(
            change_request_id=cr.id
        ).count() == 1

    def test_add_and_remove_touch_only_the_affected_rows(
        self, tenant, workspace, ctx
    ):
        kept = _requirement_artifact(tenant, workspace, "Kept")
        dropped = _requirement_artifact(tenant, workspace, "Dropped")
        added = _requirement_artifact(tenant, workspace, "Added")
        svc = ChangeRequestService()
        cr = _cr_with(svc, tenant, workspace, ctx, [kept, dropped])

        kept_row = _row(cr.id, kept.id)
        kept_pk = kept_row.pk
        kept_state = kept_row.state_before
        dropped_pk = _row(cr.id, dropped.id).pk

        svc.set_affected_items(cr_id=cr.id, item_ids=[kept.id, added.id], ctx=ctx)

        rows = {
            row.item_id: row
            for row in ChangeRequestAffectedItem.objects.filter(
                change_request_id=cr.id
            )
        }
        assert set(rows) == {str(kept.id), str(added.id)}
        assert rows[str(kept.id)].pk == kept_pk
        assert rows[str(kept.id)].state_before == kept_state
        assert not ChangeRequestAffectedItem.objects.filter(pk=dropped_pk).exists()
        # The new row is a plain manual "modify" with its own snapshot.
        assert rows[str(added.id)].origin == "manual"
        assert rows[str(added.id)].change_action == "modify"
        assert rows[str(added.id)].state_before is not None

    def test_one_version_bump_and_one_event_per_call(
        self, tenant, workspace, ctx, monkeypatch
    ):
        artifact = _requirement_artifact(tenant, workspace, "Bump")
        svc = ChangeRequestService()
        cr = _cr_with(svc, tenant, workspace, ctx, [artifact])
        cr.refresh_from_db()
        version_before = cr.version

        emitted: list = []
        monkeypatch.setattr(
            ChangeRequestService,
            "_emit_event",
            staticmethod(lambda event: emitted.append(event)),
        )

        svc.set_affected_items(cr_id=cr.id, item_ids=[artifact.id], ctx=ctx)

        cr.refresh_from_db()
        assert cr.version == version_before + 1
        updated_events = [
            e
            for e in emitted
            if e.event_type == DomainEventOutbox.EventType.CHANGE_REQUEST_UPDATED
        ]
        assert len(updated_events) == 1
        assert updated_events[0].payload == {"affected_item_count": 1}


# ---------------------------------------------------------------------------
# B) update_affected_item
# ---------------------------------------------------------------------------


class TestUpdateAffectedItem:
    def test_patch_changes_only_the_supplied_fields(
        self, tenant, workspace, ctx
    ):
        artifact = _requirement_artifact(tenant, workspace, "Patch me")
        svc = ChangeRequestService()
        cr = _cr_with(svc, tenant, workspace, ctx, [artifact])
        row = _row(cr.id, artifact.id)
        pk = row.pk
        state_before = row.state_before

        result = svc.update_affected_item(
            cr.id, artifact.id, ctx, rationale="explain why"
        )

        assert result.pk == pk
        result.refresh_from_db()
        assert result.rationale == "explain why"
        # untouched
        assert result.origin == "manual"
        assert result.change_action == "modify"
        assert result.removed_reason == ""
        assert result.state_before == state_before
        assert ChangeRequestAffectedItem.objects.filter(
            change_request_id=cr.id
        ).count() == 1

    def test_remove_requires_a_reason(self, tenant, workspace, ctx):
        artifact = _requirement_artifact(tenant, workspace, "Remove me")
        svc = ChangeRequestService()
        cr = _cr_with(svc, tenant, workspace, ctx, [artifact])

        with pytest.raises(ValidationError, match="removed_reason"):
            svc.update_affected_item(cr.id, artifact.id, ctx, change_action="remove")

        # A stored reason satisfies the gate on a later call.
        svc.update_affected_item(
            cr.id,
            artifact.id,
            ctx,
            removed_reason="decommissioned in release 2.0",
        )
        result = svc.update_affected_item(
            cr.id, artifact.id, ctx, change_action="remove"
        )
        result.refresh_from_db()
        assert result.change_action == "remove"
        assert result.removed_reason == "decommissioned in release 2.0"

    def test_unknown_change_request_raises_not_found(self, workspace, ctx):
        svc = ChangeRequestService()
        with pytest.raises(NotFoundError):
            svc.update_affected_item(uuid.uuid4(), uuid.uuid4(), ctx, rationale="x")

    def test_unknown_affected_item_raises_not_found(
        self, tenant, workspace, ctx
    ):
        artifact = _requirement_artifact(tenant, workspace, "Known")
        svc = ChangeRequestService()
        cr = _cr_with(svc, tenant, workspace, ctx, [artifact])

        with pytest.raises(NotFoundError):
            svc.update_affected_item(cr.id, uuid.uuid4(), ctx, rationale="x")

    def test_empty_payload_is_rejected(self, tenant, workspace, ctx):
        artifact = _requirement_artifact(tenant, workspace, "Empty patch")
        svc = ChangeRequestService()
        cr = _cr_with(svc, tenant, workspace, ctx, [artifact])

        with pytest.raises(ValidationError, match="at least one"):
            svc.update_affected_item(cr.id, artifact.id, ctx)

    def test_invalid_enum_values_are_rejected(self, tenant, workspace, ctx):
        artifact = _requirement_artifact(tenant, workspace, "Bad enum")
        svc = ChangeRequestService()
        cr = _cr_with(svc, tenant, workspace, ctx, [artifact])

        with pytest.raises(ValidationError, match="change_action"):
            svc.update_affected_item(cr.id, artifact.id, ctx, change_action="delete")
        with pytest.raises(ValidationError, match="origin"):
            svc.update_affected_item(cr.id, artifact.id, ctx, origin="magic")


# ---------------------------------------------------------------------------
# C) after-state capture skips removed rows
# ---------------------------------------------------------------------------


class TestAfterCaptureSkipsRemovedRows:
    def test_removed_row_stays_empty_and_modify_row_gets_state(
        self, tenant, workspace, ctx
    ):
        modified = _requirement_artifact(tenant, workspace, "Modified")
        removed = _requirement_artifact(tenant, workspace, "Removed")
        svc = ChangeRequestService()
        cr = _cr_with(svc, tenant, workspace, ctx, [modified, removed])

        svc.update_affected_item(
            cr.id, removed.id, ctx, removed_reason="retired"
        )
        svc.update_affected_item(cr.id, removed.id, ctx, change_action="remove")

        svc._capture_affected_items_after(cr=cr, tenant_id=tenant.id)

        removed_row = _row(cr.id, removed.id)
        removed_row.refresh_from_db()
        assert removed_row.state_after is None
        assert removed_row.version_after is None
        assert removed_row.removed_reason == "retired"

        modified_row = _row(cr.id, modified.id)
        modified_row.refresh_from_db()
        assert modified_row.state_after is not None
        assert modified_row.version_after == modified_row.state_after["version"]

    def test_empty_removed_reason_defaults_to_removed(
        self, tenant, workspace, ctx
    ):
        removed = _requirement_artifact(tenant, workspace, "Removed no reason")
        svc = ChangeRequestService()
        cr = _cr_with(svc, tenant, workspace, ctx, [removed])

        # Force the state directly: the service gate forbids a reasonless
        # 'remove', but historical rows may still carry one.
        ChangeRequestAffectedItem.objects.filter(change_request_id=cr.id).update(
            change_action="remove", removed_reason=""
        )

        svc._capture_affected_items_after(cr=cr, tenant_id=tenant.id)

        row = _row(cr.id, removed.id)
        row.refresh_from_db()
        assert row.state_after is None
        assert row.version_after is None
        assert row.removed_reason == "removed"
