"""Plan F F2-T2 — behavioural test for ``workflow 0024``.

``0024_seed_document_workflow_definitions`` is a data-only migration, so its
RunPython functions are exercised directly against live rows (same pattern as
``test_seed_issue_resolved_auto_approve_target_migration.py``).
"""
from __future__ import annotations

from contextlib import contextmanager
from importlib import import_module
from uuid import uuid4

import pytest
from django.apps import apps as django_apps

from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db

_mig = import_module("workflow.migrations.0024_seed_document_workflow_definitions")


@contextmanager
def _tenant_scope(tenant_id):
    TenantContext.set_tenant(tenant_id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="doc-0024", slug="doc-0024")


@pytest.fixture
def workspace(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant=tenant, name="doc-0024-ws")
    finally:
        TenantContext.clear_tenant()


def test_seed_creates_linked_definition_for_each_workspace(tenant, workspace):
    from workflow.models import GlobalWorkflowDefinition, WorkflowEngineDefinition

    with _tenant_scope(tenant.id):
        _mig.seed_document_definitions(django_apps, None)

        global_def = GlobalWorkflowDefinition.objects.get(
            tenant_id=tenant.id, item_type="Document", preset="document_default"
        )
        definition = WorkflowEngineDefinition.objects.get(
            workspace_id=str(workspace.id), item_type="Document"
        )

        assert definition.preset == "document_default"
        assert definition.is_customized is False
        assert definition.source_global_id == global_def.id
        assert definition.workflow_json["states"][0] == "Entwurf"
        assert definition.workflow_json == global_def.workflow_json


def test_seed_is_idempotent(tenant, workspace):
    from workflow.models import GlobalWorkflowDefinition, WorkflowEngineDefinition

    with _tenant_scope(tenant.id):
        _mig.seed_document_definitions(django_apps, None)
        _mig.seed_document_definitions(django_apps, None)

        assert (
            WorkflowEngineDefinition.objects.filter(item_type="Document").count() == 1
        )
        assert (
            GlobalWorkflowDefinition.objects.filter(
                item_type="Document", preset="document_default"
            ).count()
            == 1
        )


def test_reverse_refuses_while_live_item_states_exist(tenant, workspace):
    from workflow.models import WorkflowEngineDefinition, WorkflowItemState

    with _tenant_scope(tenant.id):
        _mig.seed_document_definitions(django_apps, None)
        definition = WorkflowEngineDefinition.objects.get(
            workspace_id=str(workspace.id), item_type="Document"
        )
        WorkflowItemState.objects.create(
            tenant=tenant,
            workspace=workspace,
            definition=definition,
            item_id=uuid4(),
            item_type="Document",
            current_state="Entwurf",
        )

        with pytest.raises(RuntimeError, match="live Document workflow item states"):
            _mig.unseed_document_definitions(django_apps, None)

        assert WorkflowEngineDefinition.objects.filter(item_type="Document").exists()


def test_reverse_removes_seeded_rows(tenant, workspace):
    from workflow.models import GlobalWorkflowDefinition, WorkflowEngineDefinition

    with _tenant_scope(tenant.id):
        _mig.seed_document_definitions(django_apps, None)
        _mig.unseed_document_definitions(django_apps, None)

        assert not WorkflowEngineDefinition.objects.filter(
            item_type="Document"
        ).exists()
        assert not GlobalWorkflowDefinition.objects.filter(
            item_type="Document"
        ).exists()
