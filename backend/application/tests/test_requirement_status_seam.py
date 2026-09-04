"""Requirement/Need/TestCase listing filters via the workflow engine.

Datenmodell-Konsolidierung Phase 1.
"""
import inspect
import uuid

import pytest

from application import requirement_service, stakeholder_need_service, test_service

MODULES = [requirement_service, stakeholder_need_service, test_service]


@pytest.fixture
def requirement_fixture(db):
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.models import Artifact, Requirement, Tenant, Workspace
    from persistence.tenancy import TenantContext
    from workflow.models import WorkflowEngineDefinition, WorkflowItemState

    tenant = Tenant.objects.create(name="t-req-seam")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="ws-req-seam")
    definition = WorkflowEngineDefinition.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        item_type="Requirement",
        preset="standard",
        workflow_json={"states": ["draft", "outdated"], "transitions": []},
    )
    created = []
    for state in ("draft", "outdated"):
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        req = Requirement.objects.create(
            tenant=tenant,
            artifact=artifact,
            workspace=workspace,
            title=f"REQ {state}",
            description="d",
        )
        WorkflowItemState.objects.create(
            tenant=tenant,
            item_id=req.id,
            item_type="Requirement",
            workspace_id=workspace.id,
            definition=definition,
            current_state=state,
        )
        created.append(req.id)
    ctx = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.SYSTEM,
        workspace_id=workspace.id,
    )
    return ctx, workspace.id, created[0], created[1]


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_status_column_read_remains(module):
    source = inspect.getsource(module)
    assert 'exclude(status="outdated")' not in source
    assert "status=status," not in source
    assert "from workflow import state_reader" in source


@pytest.mark.django_db
def test_outdated_requirement_is_excluded(requirement_fixture):
    from application.requirement_service import RequirementService

    ctx, workspace_id, live_id, outdated_id = requirement_fixture
    ids = {r.id for r in RequirementService().list_requirements(workspace_id, ctx)}

    assert live_id in ids
    assert outdated_id not in ids


@pytest.mark.django_db
def test_include_deleted_returns_outdated(requirement_fixture):
    from application.requirement_service import RequirementService

    ctx, workspace_id, live_id, outdated_id = requirement_fixture
    ids = {
        r.id
        for r in RequirementService().list_requirements(
            workspace_id, ctx, include_deleted=True
        )
    }

    assert {live_id, outdated_id} <= ids
