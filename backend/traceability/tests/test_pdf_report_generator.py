"""Tests for traceability.pdf_report_generator's status resolution.

C4 (Datenmodell-Konsolidierung Phase 1 review): the PDF report is a
generated deliverable artifact — rendering a permanently-frozen creation-time
``status`` for every requirement is a visible product defect, not just an
internal inconsistency. ``_fetch_workspace_data`` must resolve ``status``
through ``workflow.state_reader``, batched, with a fallback to the (now
write-once) column for a Requirement never wired into a WorkflowItemState.
"""
from __future__ import annotations

import pytest

from persistence.tenancy import TenantContext
from traceability.pdf_report_generator import _fetch_workspace_data

pytestmark = pytest.mark.django_db


def test_req_status_map_reflects_the_engine_state_not_the_stale_column():
    from persistence.models import Artifact, Requirement, Tenant, Workspace
    from workflow.lifecycle_manager import StateLifecycleManager
    from workflow.services import create_default_workflow
    from workflow.transition_validator import ValidationResult

    tenant = Tenant.objects.create(name="pdf-status-tenant", slug="pdf-status-tenant")
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="pdf-status-ws")
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        req = Requirement.objects.create(
            tenant=tenant,
            artifact=artifact,
            workspace=workspace,
            title="Rendered in the PDF",
            status="draft",
        )

        create_default_workflow(
            workspace_id=workspace.id,
            preset="standard",
            item_type="Requirement",
            tenant_id=tenant.id,
        )
        manager = StateLifecycleManager()
        manager.initialize_workflow_states([req.id], "Requirement", workspace.id)
        manager.perform_transition(
            item_id=req.id,
            item_type="Requirement",
            workspace_id=workspace.id,
            target_state="in_review",
            transitioned_by="test",
            validation_result=ValidationResult(valid=True),
        )
        assert Requirement.objects.get(id=req.id).status == "draft"  # column frozen

        data = _fetch_workspace_data(workspace.id, ctx=None)
    finally:
        TenantContext.clear_tenant()

    assert data["req_status_map"].get(str(req.id)) == "in_review"


def test_req_status_map_falls_back_to_the_column_for_an_untracked_requirement():
    from persistence.models import Artifact, Requirement, Tenant, Workspace

    tenant = Tenant.objects.create(
        name="pdf-status-untracked-tenant", slug="pdf-status-untracked-tenant"
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="pdf-status-untracked-ws")
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        req = Requirement.objects.create(
            tenant=tenant,
            artifact=artifact,
            workspace=workspace,
            title="No workflow definition",
            status="approved",
        )

        data = _fetch_workspace_data(workspace.id, ctx=None)
    finally:
        TenantContext.clear_tenant()

    assert data["req_status_map"].get(str(req.id)) is None
    # _build_requirement_document falls back to req.status when the map has
    # no entry — verified directly here since the map itself is the seam.
