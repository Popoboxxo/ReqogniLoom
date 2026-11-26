"""Regression coverage for central workflow preset resolution.

``initialize_definition`` must resolve fixed entity presets from the canonical
registry, map the two tier-driven types correctly, and reject invalid tier
values before they reach the workflow store.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext
from presets.models import WorkspacePresetConfig
from workflow.item_types import (
    WORK_ITEM_PRESET_BY_TIER,
    WORK_ITEM_TIERS,
    WORKFLOW_ITEM_TYPE_PRESETS,
)
from workflow.models import WorkflowEngineDefinition
from workflow.services import initial_state_for, initialize_definition

pytestmark = pytest.mark.django_db

_WORK_ITEM_STATES = {
    "minimal": ("todo", "in_progress", "done", "dropped"),
    "standard": ("todo", "in_progress", "blocked", "done", "dropped"),
    "extended": (
        "todo",
        "in_progress",
        "blocked",
        "in_review",
        "done",
        "dropped",
    ),
}


@contextmanager
def _tenant_scope(tenant_id):
    TenantContext.set_tenant(tenant_id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Preset Resolution Tenant", slug="preset-resolution")


def _make_workspace(
    tenant: Tenant,
    *,
    workspace_tier: object = "standard",
    config_tier: str | None = "standard",
) -> Workspace:
    with _tenant_scope(tenant.id):
        workspace = Workspace.objects.create(
            tenant=tenant,
            name=f"Preset Resolution WS {uuid.uuid4().hex[:8]}",
            preset={"tier": workspace_tier},
        )
        if config_tier is not None:
            WorkspacePresetConfig.objects.create(
                tenant=tenant,
                workspace=workspace,
                active_tier=config_tier,
            )
    return workspace


def _initialize(tenant: Tenant, workspace: Workspace, item_type: str):
    with _tenant_scope(tenant.id):
        return initialize_definition(
            workspace_id=workspace.id,
            item_type=item_type,
            tenant_id=tenant.id,
        )


def _agent_context(tenant: Tenant) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        actor_type="agent",
        agent_label="preset-resolution-test",
    )


@pytest.mark.parametrize("tier", WORK_ITEM_TIERS)
def test_valid_config_tier_drives_requirement_and_work_item(tenant, tier):
    conflicting_workspace_tier = "minimal" if tier == "extended" else "extended"
    workspace = _make_workspace(
        tenant,
        workspace_tier=conflicting_workspace_tier,
        config_tier=tier,
    )

    requirement = _initialize(tenant, workspace, "Requirement")
    work_item = _initialize(tenant, workspace, "WorkItem")

    assert requirement.preset == tier
    assert work_item.preset == WORK_ITEM_PRESET_BY_TIER[tier]
    assert work_item.states == _WORK_ITEM_STATES[tier]
    assert work_item.initial_state == "todo"
    assert "proposed" not in work_item.states
    with _tenant_scope(tenant.id):
        assert initial_state_for(_agent_context(tenant), "WorkItem", workspace.id) == "todo"


@pytest.mark.parametrize("config_tier", [None, "invalid-tier"])
def test_missing_or_invalid_config_falls_back_to_valid_workspace_tier(
    tenant, config_tier
):
    workspace = _make_workspace(
        tenant,
        workspace_tier="extended",
        config_tier=config_tier,
    )

    requirement = _initialize(tenant, workspace, "Requirement")
    work_item = _initialize(tenant, workspace, "WorkItem")
    custom_type = _initialize(tenant, workspace, "Artifact")

    assert requirement.preset == "extended"
    assert work_item.preset == "work_item_extended"
    assert custom_type.preset == "extended"


@pytest.mark.parametrize("config_tier", [None, "invalid-tier"])
@pytest.mark.parametrize("workspace_tier", ["invalid-tier", ["extended"]])
def test_missing_or_invalid_tiers_fall_back_to_standard(
    tenant, config_tier, workspace_tier
):
    workspace = _make_workspace(
        tenant,
        workspace_tier=workspace_tier,
        config_tier=config_tier,
    )

    requirement = _initialize(tenant, workspace, "Requirement")
    work_item = _initialize(tenant, workspace, "WorkItem")
    custom_type = _initialize(tenant, workspace, "Artifact")

    assert requirement.preset == "standard"
    assert work_item.preset == "work_item_standard"
    assert work_item.initial_state == "todo"
    assert "proposed" not in work_item.states
    assert custom_type.preset == "standard"


def test_document_keeps_its_fixed_registry_preset(tenant):
    workspace = _make_workspace(
        tenant,
        workspace_tier="extended",
        config_tier="invalid-tier",
    )

    document = _initialize(tenant, workspace, "Document")

    assert document.preset == WORKFLOW_ITEM_TYPE_PRESETS["Document"] == "document_default"
    assert document.initial_state == "Entwurf"


def test_work_item_initialization_is_idempotent_after_a_tier_change(tenant):
    workspace = _make_workspace(
        tenant,
        workspace_tier="minimal",
        config_tier="minimal",
    )
    first = _initialize(tenant, workspace, "WorkItem")

    with _tenant_scope(tenant.id):
        WorkspacePresetConfig.objects.filter(workspace=workspace).update(
            active_tier="extended"
        )

    second = _initialize(tenant, workspace, "WorkItem")

    assert second.preset == first.preset == "work_item_minimal"
    assert second.states == first.states == _WORK_ITEM_STATES["minimal"]
    assert second.source_global_id == first.source_global_id
    assert (
        WorkflowEngineDefinition.unscoped.filter(
            workspace_id=str(workspace.id), item_type="WorkItem"
        ).count()
        == 1
    )
