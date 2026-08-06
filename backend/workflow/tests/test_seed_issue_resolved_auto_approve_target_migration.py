"""GH-370 — data-migration test for
``workflow.migrations.0013_seed_issue_resolved_auto_approve_target``.

Exercises the real ``seed_auto_approve_targets`` RunPython function against
live ``GlobalWorkflowDefinition`` / ``WorkflowEngineDefinition`` rows, the
same way the schema-unchanged backfill in 0011 works (no migration-state
harness needed since no field/table shape changed, only JSON data).
"""
from __future__ import annotations

from contextlib import contextmanager
from importlib import import_module
from uuid import uuid4

import pytest
from django.apps import apps as django_apps

from persistence.models import Tenant
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db

_mig = import_module(
    "workflow.migrations.0013_seed_issue_resolved_auto_approve_target"
)
seed_auto_approve_targets = _mig.seed_auto_approve_targets


@contextmanager
def _tenant_scope(tenant_id):
    """GlobalWorkflowDefinition / WorkflowEngineDefinition are
    TenantScopedModel (ADR-03) -- their default manager requires an active
    TenantContext for every query, same idiom as
    test_review_tool_group.py's ``workspace`` fixture."""
    TenantContext.set_tenant(tenant_id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="gh370-tenant", slug="gh370-tenant")


def _issue_workflow_json_without_resolved_target() -> dict:
    return {
        "states": ["Open", "In Progress", "Resolved", "Closed", "Wontfix"],
        "transitions": [],
        "state_meta": {"Wontfix": {"is_outdated_equivalent": True}},
    }


def test_migration_seeds_resolved_auto_approve_target_on_global_definition(tenant):
    from workflow.models import GlobalWorkflowDefinition

    with _tenant_scope(tenant.id):
        global_def = GlobalWorkflowDefinition.objects.create(
            tenant=tenant,
            item_type="Issue",
            preset="issue_default",
            workflow_json=_issue_workflow_json_without_resolved_target(),
        )

        seed_auto_approve_targets(django_apps, None)

        global_def.refresh_from_db()
        assert global_def.workflow_json["state_meta"]["Resolved"] == {
            "auto_approve_target": True
        }
        # Pre-existing state_meta entries survive the merge.
        assert global_def.workflow_json["state_meta"]["Wontfix"] == {
            "is_outdated_equivalent": True
        }


def test_migration_propagates_to_non_customized_workspace_definitions(tenant):
    from workflow.models import GlobalWorkflowDefinition, WorkflowEngineDefinition

    with _tenant_scope(tenant.id):
        global_def = GlobalWorkflowDefinition.objects.create(
            tenant=tenant,
            item_type="Issue",
            preset="issue_default",
            workflow_json=_issue_workflow_json_without_resolved_target(),
        )
        non_customized = WorkflowEngineDefinition.objects.create(
            tenant=tenant,
            workspace_id=uuid4(),
            item_type="Issue",
            preset="issue_default",
            workflow_json=_issue_workflow_json_without_resolved_target(),
            source_global=global_def,
            is_customized=False,
        )
        customized = WorkflowEngineDefinition.objects.create(
            tenant=tenant,
            workspace_id=uuid4(),
            item_type="Issue",
            preset="issue_default",
            workflow_json=_issue_workflow_json_without_resolved_target(),
            source_global=global_def,
            is_customized=True,
        )

        seed_auto_approve_targets(django_apps, None)

        non_customized.refresh_from_db()
        customized.refresh_from_db()
        assert (
            non_customized.workflow_json["state_meta"]["Resolved"]["auto_approve_target"]
            is True
        )
        # A workspace that already diverged from the global default is left alone.
        assert "Resolved" not in customized.workflow_json.get("state_meta", {})


def test_migration_backfills_orphaned_workspace_rows_with_no_global_link(tenant):
    """Pre-REQ-178 rows (no ``source_global``) are still backfilled directly
    by ``preset`` name, same as the ``source_global``-linked rows."""
    from workflow.models import WorkflowEngineDefinition

    with _tenant_scope(tenant.id):
        orphaned = WorkflowEngineDefinition.objects.create(
            tenant=tenant,
            workspace_id=uuid4(),
            item_type="Issue",
            preset="issue_default",
            workflow_json=_issue_workflow_json_without_resolved_target(),
            source_global=None,
            is_customized=False,
        )

        seed_auto_approve_targets(django_apps, None)

        orphaned.refresh_from_db()
        assert (
            orphaned.workflow_json["state_meta"]["Resolved"]["auto_approve_target"]
            is True
        )


def test_migration_is_idempotent(tenant):
    from workflow.models import GlobalWorkflowDefinition

    with _tenant_scope(tenant.id):
        global_def = GlobalWorkflowDefinition.objects.create(
            tenant=tenant,
            item_type="Issue",
            preset="issue_default",
            workflow_json=_issue_workflow_json_without_resolved_target(),
        )

        seed_auto_approve_targets(django_apps, None)
        seed_auto_approve_targets(django_apps, None)

        global_def.refresh_from_db()
        assert global_def.workflow_json["state_meta"]["Resolved"] == {
            "auto_approve_target": True
        }


def test_migration_ignores_unrelated_presets(tenant):
    from workflow.models import GlobalWorkflowDefinition

    with _tenant_scope(tenant.id):
        unrelated = GlobalWorkflowDefinition.objects.create(
            tenant=tenant,
            item_type="Adr",
            preset="adr_default",
            workflow_json={
                "states": ["Draft", "Approved"],
                "transitions": [],
                "state_meta": {},
            },
        )

        seed_auto_approve_targets(django_apps, None)

        unrelated.refresh_from_db()
        assert "Resolved" not in unrelated.workflow_json.get("state_meta", {})
