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

    result = ReleaseService().release_element(
        element_id=root.id, ctx=ctx, change_reason="Release for milestone M1"
    )

    assert result["release_state"] == "released"
    assert result["elements_released"] == 2
    assert result["requirements_released"] == 1

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
