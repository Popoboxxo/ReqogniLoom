"""Release cascade (ADR-028 A1): impact preview, element and requirement release."""

from __future__ import annotations

import pytest

from application.base import ValidationError
from application.release_service import ReleaseService
from auth_tenancy.context import AuthContext
from persistence.models import (
    Allocation,
    AllocationStatus,
    ArchitectureElement,
    Artifact,
    Requirement,
    Tenant,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext
from workflow.definition_store import WorkflowDefinitionStore
from workflow.lifecycle_manager import StateLifecycleManager
from workflow.models import WorkflowItemState

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="Release Tenant", slug="release-tenant")


@pytest.fixture(autouse=True)
def _tenant_context(tenant: Tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username="release-user", email="release@example.com", tenant=tenant
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    workspace = Workspace.objects.create(
        tenant=tenant, name="Release-WS", preset={"name": "extended"}
    )
    store = WorkflowDefinitionStore()
    for item_type in ("ArchitectureElement", "Requirement"):
        store.create_workspace_default_workflow(
            workspace_id=workspace.id,
            preset="extended",
            item_type=item_type,
            tenant_id=tenant.id,
        )
    return workspace


@pytest.fixture
def ctx(user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant_id,
        active_roles=("admin",),
        auth_method="test",
        api_key_id=None,
    )


def _element(tenant: Tenant, workspace: Workspace, title: str, parent=None):
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="ArchitectureElement"
    )
    return ArchitectureElement.objects.create(
        tenant=tenant, workspace=workspace, artifact=artifact, title=title, parent=parent
    )


def _set_state(item_id, item_type: str, workspace: Workspace, state: str) -> None:
    lifecycle = StateLifecycleManager()
    lifecycle.ensure_item_state(item_id, item_type, workspace.id, "draft")
    WorkflowItemState.objects.filter(
        item_id=item_id, item_type=item_type, workspace_id=workspace.id
    ).update(current_state=state)


def _set_tier(requirement: Requirement, tier_key: str) -> None:
    Requirement.objects.filter(id=requirement.id).update(tier_key=tier_key)
    requirement.refresh_from_db()


def _requirement(tenant: Tenant, workspace: Workspace) -> Requirement:
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    requirement = Requirement.objects.create(
        tenant=tenant, workspace=workspace, artifact=artifact, title="R", type="SyReq"
    )
    _set_state(requirement.id, "Requirement", workspace, "approved")
    return requirement


def _build_tree(tenant: Tenant, workspace: Workspace):
    root = _element(tenant, workspace, "System")
    child = _element(tenant, workspace, "Subsystem", parent=root)
    for element in (root, child):
        _set_state(element.id, "ArchitectureElement", workspace, "approved")

    requirement = _requirement(tenant, workspace)
    Allocation.objects.create(
        tenant=tenant,
        workspace=workspace,
        requirement_artifact=requirement.artifact,
        element_artifact=child.artifact,
        status=AllocationStatus.DRAFT,
        is_primary=True,
    )
    return root, child, requirement


def test_impact_counts_the_whole_subtree(
    tenant: Tenant, workspace: Workspace, ctx: AuthContext
) -> None:
    root, _child, _requirement = _build_tree(tenant, workspace)

    impact = ReleaseService().impact(element_id=root.id, ctx=ctx)

    assert impact.release_state == "released"
    assert impact.allowed_source_states == ("approved", "verified")
    assert impact.descendant_elements == 1
    assert impact.requirements_total == 1
    assert impact.requirements_releasable == 1
    assert impact.requirements_by_state == {"approved": 1}
    assert impact.content_freeze is True
    assert impact.async_required is False


def test_release_element_cascades_to_children_and_requirements(
    tenant: Tenant, workspace: Workspace, ctx: AuthContext
) -> None:
    from application.artifact_freeze import is_frozen

    root, child, requirement = _build_tree(tenant, workspace)
    _set_tier(requirement, "L2")

    result = ReleaseService().release_element(
        element_id=root.id, ctx=ctx, change_reason="Release for milestone M1"
    )

    assert result["release_state"] == "released"
    assert result["elements_released"] == 2
    assert result["requirements_released"] == 1
    assert result["content_snapshots"] == 1
    assert result["pinned_tiers"] == 1

    states = dict(
        WorkflowItemState.objects.filter(
            workspace_id=workspace.id, item_type="ArchitectureElement"
        ).values_list("item_id", "current_state")
    )
    assert states[root.id] == "released"
    assert states[child.id] == "released"
    requirement_state = WorkflowItemState.objects.get(
        item_id=requirement.id, item_type="Requirement", workspace_id=workspace.id
    )
    assert requirement_state.current_state == "released"
    assert is_frozen(root.artifact) is not None


def test_a_draft_element_cannot_be_released(
    tenant: Tenant, workspace: Workspace, ctx: AuthContext
) -> None:
    root = _element(tenant, workspace, "Draft System")
    _set_state(root.id, "ArchitectureElement", workspace, "draft")

    with pytest.raises(ValidationError) as excinfo:
        ReleaseService().release_element(
            element_id=root.id, ctx=ctx, change_reason="too early"
        )

    assert "only allowed from" in str(excinfo.value)


def test_releasing_a_requirement_twice_is_a_no_op_success(
    tenant: Tenant, workspace: Workspace, ctx: AuthContext
) -> None:
    _root, _child, requirement = _build_tree(tenant, workspace)
    service = ReleaseService()

    first = service.release_requirement(
        requirement_id=requirement.id, ctx=ctx, change_reason="Release"
    )
    second = service.release_requirement(
        requirement_id=requirement.id, ctx=ctx, change_reason="Again"
    )

    assert first["released"] is True
    assert second["released"] is False
    assert second["reason"] == "already released"


def test_release_pins_the_tier_and_mirrors_the_allocation(
    tenant: Tenant, workspace: Workspace, ctx: AuthContext
) -> None:
    from persistence.models import ArtifactVersion

    root, _child, requirement = _build_tree(tenant, workspace)
    _set_tier(requirement, "L2")

    ReleaseService().release_element(
        element_id=root.id, ctx=ctx, change_reason="Release for milestone M1"
    )

    requirement.refresh_from_db()
    assert requirement.released_tier_key == "L2"

    allocation = Allocation.objects.get(requirement_artifact=requirement.artifact)
    assert allocation.status == AllocationStatus.RELEASED
    assert allocation.released_at is not None
    assert allocation.released_by_id == ctx.user_id

    snapshot = ArtifactVersion.objects.get(artifact=requirement.artifact)
    assert snapshot.payload["tier_key"] == "L2"
    assert snapshot.payload["released_state"] == "released"


def test_standard_has_no_content_snapshot_but_still_pins_the_tier(
    tenant: Tenant, ctx: AuthContext
) -> None:
    from persistence.models import ArtifactVersion

    workspace = Workspace.objects.create(
        tenant=tenant, name="Standard-WS", preset={"name": "standard"}
    )
    store = WorkflowDefinitionStore()
    for item_type in ("ArchitectureElement", "Requirement"):
        store.create_workspace_default_workflow(
            workspace_id=workspace.id,
            preset="standard",
            item_type=item_type,
            tenant_id=tenant.id,
        )
    root, _child, requirement = _build_tree(tenant, workspace)
    _set_tier(requirement, "L1")
    # The standard schema has no in_review step; approved is a valid source.
    assert ArtifactVersion.objects.filter(artifact=requirement.artifact).count() == 0

    result = ReleaseService().release_element(
        element_id=root.id, ctx=ctx, change_reason="Standard release"
    )

    requirement.refresh_from_db()
    assert result["content_snapshots"] == 0
    assert result["content_freeze"] is False
    assert requirement.released_tier_key == "L1"
    assert ArtifactVersion.objects.filter(artifact=requirement.artifact).count() == 0


def test_a_release_writes_one_audit_entry(
    tenant: Tenant, workspace: Workspace, ctx: AuthContext
) -> None:
    from audit.models import AuditEntry

    root, _child, _requirement = _build_tree(tenant, workspace)
    before = AuditEntry.objects.count()

    ReleaseService().release_element(
        element_id=root.id, ctx=ctx, change_reason="Release for milestone M1"
    )

    assert AuditEntry.objects.count() == before + 1
    entry = AuditEntry.objects.order_by("-created_at").first()
    assert entry.entity_id == root.id
    assert entry.details["release_state"] == "released"


def test_an_element_with_allocations_requires_a_requirement_release_state(
    tenant: Tenant, ctx: AuthContext
) -> None:
    workspace = Workspace.objects.create(
        tenant=tenant, name="Element-only-WS", preset={"name": "standard"}
    )
    # Only the element lifecycle is configured — a release must not silently
    # leave the allocated requirements behind.
    WorkflowDefinitionStore().create_workspace_default_workflow(
        workspace_id=workspace.id,
        preset="standard",
        item_type="ArchitectureElement",
        tenant_id=tenant.id,
    )
    root = _element(tenant, workspace, "System")
    _set_state(root.id, "ArchitectureElement", workspace, "approved")
    # A requirement row with no workflow state at all — the release must refuse
    # before it touches anything, not release the element and leave it behind.
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    requirement = Requirement.objects.create(
        tenant=tenant, workspace=workspace, artifact=artifact, title="R", type="SyReq"
    )
    Allocation.objects.create(
        tenant=tenant,
        workspace=workspace,
        requirement_artifact=artifact,
        element_artifact=root.artifact,
        status=AllocationStatus.DRAFT,
        is_primary=True,
    )

    with pytest.raises(ValidationError) as excinfo:
        ReleaseService().release_element(
            element_id=root.id, ctx=ctx, change_reason="Release"
        )

    assert "for Requirement" in str(excinfo.value)


def test_the_baseline_capture_prefers_the_pinned_tier(
    tenant: Tenant, workspace: Workspace, ctx: AuthContext
) -> None:
    """ADR-028 D11: after a re-allocation the baseline still shows the release tier."""
    from baseline.state_capture import capture_states
    from baseline.types import DeltaIndexTuple

    root, _child, requirement = _build_tree(tenant, workspace)
    _set_tier(requirement, "L2")
    ReleaseService().release_element(
        element_id=root.id, ctx=ctx, change_reason="Release for milestone M1"
    )

    # A later re-allocation moves the live tier; the pin must win.
    Requirement.objects.filter(id=requirement.id).update(tier_key="L0")

    captured = capture_states(
        [
            DeltaIndexTuple(
                item_id=str(requirement.artifact_id), version=1, entity_type="item"
            )
        ],
        tenant.id,
    )

    state = captured[str(requirement.artifact_id)]
    assert state["tier_key"] == "L2"
    assert state["released_tier_key"] == "L2"
