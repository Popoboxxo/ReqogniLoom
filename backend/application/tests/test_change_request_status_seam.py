"""ChangeRequest listing/transition run off the workflow engine.

Datenmodell-Konsolidierung Phase 1.
"""
import inspect
import uuid

import pytest

from application import change_request_service
from persistence.models import Artifact


@pytest.fixture
def cr_fixture(db):
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.models import Tenant, Workspace
    from persistence.tenancy import TenantContext
    from workflow.models import WorkflowEngineDefinition, WorkflowItemState

    from application.models import ChangeRequest

    tenant = Tenant.objects.create(name="t-cr-seam")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="ws-cr-seam")
    definition = WorkflowEngineDefinition.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        item_type="ChangeRequest",
        preset="standard",
        workflow_json={
            "states": ["draft", "under_review", "outdated"],
            "transitions": [],
        },
    )
    created = {}
    for state in ("draft", "under_review", "outdated"):
        # Phase 4 (D-3): the soft-delete flag lives on the backing Artifact,
        # which ChangeRequest gained in Task 18/19 — so these rows need one.
        # ``current_state`` is left as-is so this keeps exercising the legacy
        # shape workflow/0018 cleans up.
        artifact = Artifact.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type="ChangeRequest",
            lifecycle_status="outdated" if state == "outdated" else "active",
        )
        cr = ChangeRequest.objects.create(
            workspace_id=workspace.id,
            tenant_id=tenant.id,
            artifact=artifact,
            title=f"CR {state}",
        )
        WorkflowItemState.objects.create(
            tenant=tenant,
            item_id=cr.id,
            item_type="ChangeRequest",
            workspace_id=workspace.id,
            definition=definition,
            current_state=state,
        )
        created[state] = cr.id
    ctx = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.SYSTEM,
        workspace_id=workspace.id,
    )
    return ctx, workspace.id, created


def test_no_status_column_read_remains():
    source = inspect.getsource(change_request_service)
    assert "status=status_filter" not in source
    assert 'exclude(status="outdated")' not in source
    assert 'refresh_from_db(fields=["version", "status", "change_reason"])' not in source
    assert "from workflow import state_reader" in source


@pytest.mark.django_db
def test_outdated_is_excluded_by_default(cr_fixture):
    from application.change_request_service import ChangeRequestService

    ctx, workspace_id, created = cr_fixture
    ids = {
        cr.id
        for cr in ChangeRequestService().list_change_requests(workspace_id, ctx)
    }

    assert created["draft"] in ids
    assert created["outdated"] not in ids


@pytest.mark.django_db
def test_status_filter_matches_engine_state(cr_fixture):
    from application.change_request_service import ChangeRequestService

    ctx, workspace_id, created = cr_fixture
    result = ChangeRequestService().list_change_requests(
        workspace_id, ctx, status_filter="under_review"
    )

    assert [cr.id for cr in result] == [created["under_review"]]
