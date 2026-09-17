"""
Tests for the universal outdate()/reactivate() escape hatch (Task 2, Phase 0
status-unification).

Datenmodell-Konsolidierung Phase 4 (Decision D-3) changed what these two
functions write: soft-delete is now the ``Artifact.lifecycle_status`` flag and
the item's ``WorkflowItemState.current_state`` is left untouched. The
assertions below were rewritten accordingly — they used to check
``current_state == "outdated"`` and a ``WorkflowHistoryEntry`` into
``"outdated"``, neither of which exists anymore because no workflow transition
happens.

Covers:
  - outdate() flags an item from any current state, bypassing the normal
    preset-transition-list validation, without disturbing that state.
  - reactivate() clears the flag, likewise without touching the state.
  - reactivate() raises ValueError when the item is not currently outdated.
"""
from __future__ import annotations

import uuid

import pytest

from persistence.models import Artifact, Requirement, Tenant, Workspace
from persistence.tenancy import TenantContext
from workflow.models import WorkflowItemState
from workflow.services import create_default_workflow, outdate, reactivate


def _flag_of(item_id):
    """Return the soft-delete flag on a Requirement's backing Artifact."""
    artifact_id = Requirement.objects.values_list("artifact_id", flat=True).get(
        pk=item_id
    )
    return Artifact.objects.get(pk=artifact_id).lifecycle_status


@pytest.fixture(autouse=True)
def _clear_tenant_context():
    """Avoid TenantContext bleed between tests (REQ-L3-PL002-002)."""
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Outdate Test Tenant", slug="outdate-test-tenant")


@pytest.fixture
def workspace(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant=tenant, name="Outdate Test Workspace")
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def auth_ctx(tenant):
    from auth_tenancy.context import AuthContext

    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method="test",
    )


@pytest.fixture
def requirement_with_workflow(db, tenant, workspace, auth_ctx):
    """Create a Requirement with an initialised WorkflowItemState ("draft").

    Uses RequirementService.create_requirement (not a raw Requirement.objects
    .create) because Requirement has no workspace_id field of its own — the
    workspace link lives on the backing Artifact — and because the workflow
    state must actually be initialised for force_transition() to find a row
    to lock.
    """
    from application.requirement_service import RequirementService

    TenantContext.set_tenant(tenant.id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="standard",
            item_type="Requirement",
            tenant_id=tenant.id,
        )

        service = RequirementService()
        requirement = service.create_requirement(
            workspace_id=workspace.id,
            title="Test Req",
            ctx=auth_ctx,
        )
    finally:
        TenantContext.clear_tenant()
    return requirement.id, workspace.id


@pytest.mark.django_db
def test_outdate_flags_from_any_current_state(requirement_with_workflow, auth_ctx):
    """Phase 4 (D-3): the flag goes on the Artifact, the state stays put.

    Pre-Phase-4 this asserted ``current_state == "outdated"`` plus a
    ``WorkflowHistoryEntry`` carrying ``reason``. Neither applies now: no
    transition happens, so the engine writes no history — the soft-delete is
    recorded by the calling service's ``AuditEntry`` instead.
    """
    item_id, workspace_id = requirement_with_workflow

    # workflow.services operates on the tenant-scoped manager directly — the
    # caller (normally an application-layer service) must set TenantContext
    # before invoking any StateLifecycleManager method.
    TenantContext.set_tenant(auth_ctx.tenant_id)
    try:
        result = outdate(
            item_id=item_id,
            item_type="Requirement",
            workspace_id=workspace_id,
            ctx=auth_ctx,
            reason="superseded by REQ-99",
        )

        # The result reports the *lifecycle* move; the workflow state is what
        # stayed put, which is the whole point of D-3.
        assert result.previous_state == "draft"
        assert result.new_state == "outdated"
        assert result.history_entry_id is None
        item_state = WorkflowItemState.objects.get(item_id=item_id, item_type="Requirement")
        assert item_state.current_state == "draft"
        assert _flag_of(item_id) == "outdated"
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_reactivate_clears_the_flag_and_leaves_the_state(
    requirement_with_workflow, auth_ctx
):
    """Phase 4 (D-3): there is nothing to "restore" — the state never moved.

    The state assertion is deliberately kept identical to the pre-Phase-4
    version ("draft" round-trips) because the *observable* outcome for a caller
    is unchanged; what changed is that it no longer depends on a
    ``WorkflowHistoryEntry`` walk. The flag assertion is what is new.
    """
    item_id, workspace_id = requirement_with_workflow

    TenantContext.set_tenant(auth_ctx.tenant_id)
    try:
        outdate(
            item_id=item_id,
            item_type="Requirement",
            workspace_id=workspace_id,
            ctx=auth_ctx,
            reason="test",
        )
        assert _flag_of(item_id) == "outdated"

        result = reactivate(
            item_id=item_id, item_type="Requirement", workspace_id=workspace_id, ctx=auth_ctx
        )

        assert result.new_state == "draft"
        item_state = WorkflowItemState.objects.get(item_id=item_id, item_type="Requirement")
        assert item_state.current_state == "draft"
        assert _flag_of(item_id) == "active"
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_reactivate_raises_if_not_currently_outdated(requirement_with_workflow, auth_ctx):
    item_id, workspace_id = requirement_with_workflow

    TenantContext.set_tenant(auth_ctx.tenant_id)
    try:
        with pytest.raises(ValueError, match="item is not outdated"):
            reactivate(
                item_id=item_id,
                item_type="Requirement",
                workspace_id=workspace_id,
                ctx=auth_ctx,
            )
    finally:
        TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# Regression (Phase 0 final review, Fund 2): outdate() must self-heal a
# missing WorkflowItemState instead of crashing with DoesNotExist. Previously
# only documented for GlossaryTerm (legacy pre-workflow data), but nothing
# prevents any entity type from reaching outdate() without an item state --
# e.g. a definition exists but initialize_workflow_states() was never called
# for a particular item.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_outdate_self_heals_missing_workflow_item_state(tenant, workspace, auth_ctx):
    """An item with a workflow definition but NO WorkflowItemState row must
    still be outdate()-able (no DoesNotExist crash).

    Phase 4 (D-3): it now lands on the definition's initial state with the
    soft-delete flag set, rather than in a hijacked "outdated" state. The row
    is still created — the transitions API needs it to offer moves once the
    item is reactivated.
    """
    TenantContext.set_tenant(tenant.id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="standard",
            item_type="Requirement",
            tenant_id=tenant.id,
        )

        # Create the Requirement directly via the ORM (bypassing
        # RequirementService.create_requirement(), which would normally call
        # initialize_workflow_states()) to simulate a legacy row that never
        # got a WorkflowItemState.
        artifact = Artifact.objects.create(workspace=workspace, artifact_type="requirement")
        requirement = Requirement.objects.create(
            tenant=tenant, artifact=artifact, title="Legacy Requirement"
        )

        assert not WorkflowItemState.objects.filter(
            item_id=requirement.id, item_type="Requirement"
        ).exists()

        result = outdate(
            item_id=requirement.id,
            item_type="Requirement",
            workspace_id=workspace.id,
            ctx=auth_ctx,
            reason="legacy row soft-delete",
        )

        assert result.new_state == "outdated"
        item_state = WorkflowItemState.objects.get(
            item_id=requirement.id, item_type="Requirement"
        )
        assert item_state.current_state == "draft"
        assert _flag_of(requirement.id) == "outdated"
    finally:
        TenantContext.clear_tenant()
