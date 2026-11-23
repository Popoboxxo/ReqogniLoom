"""#2012 — a structured criteria write unblocks the standard release gate.

The release gate (``workflow.precondition_rules.check_mandatory_fields``) checks
the legacy free-text ``acceptance_criteria`` column, while the MCP structured
write used to populate only ``acceptance_criteria_items``. A requirement whose
criteria were authored over MCP therefore stayed blocked forever in
standard/extended. This test pins that the synchronous mirror materialization
removes the blockade without weakening the gate itself.
"""
from __future__ import annotations

import pytest

from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def standard_env(db):
    from application.workspace_service import WorkspaceService
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.models import Artifact, Requirement, Tenant, User

    tenant = Tenant.objects.create(name="t-2012-gate", slug="t-2012-gate")
    TenantContext.set_tenant(tenant.id)
    user = User.objects.create(
        username="u-2012-gate", email="u-2012-gate@example.com", tenant=tenant
    )
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    workspace = WorkspaceService().create_workspace(
        ctx, name="ws-2012-standard", preset="standard"
    )
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    requirement = Requirement.objects.create(
        tenant=tenant,
        artifact=artifact,
        title="Gate requirement",
        description="A description",
        # acceptance_criteria deliberately left empty.
    )
    try:
        yield tenant, workspace, requirement, ctx
    finally:
        TenantContext.clear_tenant()


def _gate_error(workspace, requirement):
    from workflow.precondition_rules import check_mandatory_fields

    return check_mandatory_fields(
        item_type="Requirement",
        item_id=requirement.id,
        target_state="approved",
        workspace_id=str(workspace.id),
        change_reason="Fixture reason",
    )


def test_structured_criteria_write_satisfies_the_standard_release_gate(
    standard_env,
) -> None:
    from application.requirement_service import RequirementService

    _tenant, workspace, requirement, ctx = standard_env

    # Before: the gate sees the empty legacy text column and blocks.
    error = _gate_error(workspace, requirement)
    assert error is not None
    assert "acceptance_criteria" in error[1]

    # MCP structured write (same service path as the tool).
    RequirementService().set_acceptance_criteria(
        requirement.id,
        ctx,
        [{"text": "The system shall be fast", "fulfilled": False}],
        change_reason="#2012",
    )
    requirement.refresh_from_db()

    # The mirror is populated and the (unchanged) gate now passes.
    assert requirement.acceptance_criteria == "The system shall be fast"
    assert _gate_error(workspace, requirement) is None
