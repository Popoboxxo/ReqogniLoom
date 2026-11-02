"""Plan F F3-T2 — behavioural test for ``workflow 0025``.

``0025_seed_work_item_workflow_definitions`` is a data-only migration, so its
RunPython functions are exercised directly against live rows (same pattern as
``test_seed_document_workflow_definitions_migration.py``).
"""
from __future__ import annotations

from contextlib import contextmanager
from importlib import import_module
from uuid import uuid4

import pytest
from django.apps import apps as django_apps

from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext
from presets.models import WorkspacePresetConfig

pytestmark = pytest.mark.django_db

_mig = import_module("workflow.migrations.0025_seed_work_item_workflow_definitions")


@contextmanager
def _tenant_scope(tenant_id):
    TenantContext.set_tenant(tenant_id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


def _workspace(tenant, name, tier) -> Workspace:
    with _tenant_scope(tenant.id):
        workspace = Workspace.objects.create(
            tenant=tenant, name=name, preset={"tier": tier}
        )
        WorkspacePresetConfig.objects.create(
            tenant=tenant,
            workspace=workspace,
            active_tier=tier,
        )
        return workspace


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="wi-0025", slug="wi-0025")


@pytest.fixture
def workspace_extended(tenant):
    return _workspace(tenant, "wi-0025-extended", "extended")


def test_seed_creates_all_globals_and_the_tier_matched_definition(
    tenant, workspace_extended
):
    from workflow.models import GlobalWorkflowDefinition, WorkflowEngineDefinition

    with _tenant_scope(tenant.id):
        _mig.seed_work_item_definitions(django_apps, None)

        globals_ = set(
            GlobalWorkflowDefinition.objects.filter(
                tenant_id=tenant.id, item_type="WorkItem"
            ).values_list("preset", flat=True)
        )
        definition = WorkflowEngineDefinition.objects.get(
            workspace_id=str(workspace_extended.id), item_type="WorkItem"
        )
        global_extended = GlobalWorkflowDefinition.objects.get(
            tenant_id=tenant.id,
            item_type="WorkItem",
            preset="work_item_extended",
        )

    assert globals_ == {
        "work_item_minimal",
        "work_item_standard",
        "work_item_extended",
    }
    assert definition.preset == "work_item_extended"
    assert definition.is_customized is False
    assert definition.source_global_id == global_extended.id
    assert definition.workflow_json == global_extended.workflow_json
    assert definition.workflow_json["states"][0] == "todo"


def test_seed_resolves_each_workspaces_own_tier(tenant):
    from workflow.models import WorkflowEngineDefinition

    minimal = _workspace(tenant, "wi-0025-minimal", "minimal")
    standard = _workspace(tenant, "wi-0025-standard", "standard")

    with _tenant_scope(tenant.id):
        _mig.seed_work_item_definitions(django_apps, None)

        presets = dict(
            WorkflowEngineDefinition.objects.filter(
                item_type="WorkItem"
            ).values_list("workspace_id", "preset")
        )

    assert presets[minimal.id] == "work_item_minimal"
    assert presets[standard.id] == "work_item_standard"


def test_seed_is_idempotent(tenant, workspace_extended):
    from workflow.models import GlobalWorkflowDefinition, WorkflowEngineDefinition

    with _tenant_scope(tenant.id):
        _mig.seed_work_item_definitions(django_apps, None)
        _mig.seed_work_item_definitions(django_apps, None)

        assert WorkflowEngineDefinition.objects.filter(
            item_type="WorkItem"
        ).count() == 1
        assert (
            GlobalWorkflowDefinition.objects.filter(
                item_type="WorkItem"
            ).count()
            == 3
        )


def test_reverse_refuses_while_live_item_states_exist(tenant, workspace_extended):
    from workflow.models import WorkflowEngineDefinition, WorkflowItemState

    with _tenant_scope(tenant.id):
        _mig.seed_work_item_definitions(django_apps, None)
        definition = WorkflowEngineDefinition.objects.get(
            workspace_id=str(workspace_extended.id), item_type="WorkItem"
        )
        WorkflowItemState.objects.create(
            tenant=tenant,
            workspace=workspace_extended,
            definition=definition,
            item_id=uuid4(),
            item_type="WorkItem",
            current_state="todo",
        )

        with pytest.raises(RuntimeError, match="live WorkItem workflow item states"):
            _mig.unseed_work_item_definitions(django_apps, None)

        assert WorkflowEngineDefinition.objects.filter(item_type="WorkItem").exists()


def test_reverse_removes_seeded_rows(tenant, workspace_extended):
    from workflow.models import GlobalWorkflowDefinition, WorkflowEngineDefinition

    with _tenant_scope(tenant.id):
        _mig.seed_work_item_definitions(django_apps, None)
        _mig.unseed_work_item_definitions(django_apps, None)

        assert not WorkflowEngineDefinition.objects.filter(
            item_type="WorkItem"
        ).exists()
        assert not GlobalWorkflowDefinition.objects.filter(
            item_type="WorkItem"
        ).exists()
