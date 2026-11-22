"""Issue #2016 — the CCB graph had no discoverable MCP entry point.

The ``ccb_approval`` preset defines ``draft -> submitted`` (editor/admin,
change_reason required), but the ``change_request`` MCP group only published
CRUD plus outdate/reactivate and ``change_request.update`` rejects ``status``.
The only workaround was ``artifact.bulk_transition`` -- invisible to an agent
browsing ``tools/list``. This suite pins the new, dedicated tool.
"""
from __future__ import annotations

import pytest

from auth_tenancy.context import AuthContext
from mcp_server.tools.change_request import ChangeRequestToolGroup
from persistence.models import Tenant, User
from persistence.models import Workspace as PersistenceWorkspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db

_API_KEY = "reqlo_testkey_cr_submit_2016"


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="cr-tenant-2016", slug="cr-tenant-2016")


@pytest.fixture
def user(tenant):
    return User.objects.create(
        username="cruser2016", email="cr2016@example.com", tenant=tenant
    )


@pytest.fixture
def ctx(user):
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="cr-tenant-2016",
    )


@pytest.fixture
def workspace(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        return PersistenceWorkspace.objects.create(
            tenant=tenant, name="cr-ws-2016", preset={"name": "standard"}
        )
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def cr_workflow(ctx, workspace):
    from workflow.services import create_default_workflow

    TenantContext.set_tenant(ctx.tenant_id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="ccb_approval",
            item_type="ChangeRequest",
            tenant_id=ctx.tenant_id,
        )
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def draft_cr(ctx, workspace, cr_workflow):
    from application.change_request_service import ChangeRequestService

    TenantContext.set_tenant(ctx.tenant_id)
    try:
        return ChangeRequestService().create_change_request(
            workspace_id=workspace.id,
            title="Submit me to CCB",
            ctx=ctx,
            description="Replace session auth with 2FA",
            change_reason="security hardening",
        )
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def group():
    return ChangeRequestToolGroup()


def _submit(group, ctx, workspace, cr_id, **overrides):
    params = {
        "id": str(cr_id),
        "workspace_id": str(workspace.id),
        "change_reason": "ready for CCB review",
    }
    params.update(overrides)
    TenantContext.set_tenant(ctx.tenant_id)
    try:
        return group.execute_tool(
            "change_request.submit_for_review", params, ctx, _API_KEY
        )
    finally:
        TenantContext.clear_tenant()


def test_submit_for_review_moves_draft_to_submitted(group, ctx, workspace, draft_cr):
    result = _submit(group, ctx, workspace, draft_cr.id)
    assert result.success is True, result.message
    assert result.data["new_state"] == "submitted"


def test_submit_for_review_is_persisted(group, ctx, workspace, draft_cr):
    from application.change_request_service import ChangeRequestService
    from workflow.state_reader import current_state

    result = _submit(group, ctx, workspace, draft_cr.id)
    assert result.success is True, result.message
    TenantContext.set_tenant(ctx.tenant_id)
    try:
        assert current_state("ChangeRequest", draft_cr.id) == "submitted"
        assert ChangeRequestService().get_change_request(draft_cr.id, ctx).version >= 2
    finally:
        TenantContext.clear_tenant()


def test_submit_for_review_requires_change_reason(group, ctx, workspace, draft_cr):
    result = _submit(group, ctx, workspace, draft_cr.id, change_reason="")
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_submit_for_review_refuses_a_second_submit(group, ctx, workspace, draft_cr):
    first = _submit(group, ctx, workspace, draft_cr.id)
    assert first.success is True, first.message
    second = _submit(group, ctx, workspace, draft_cr.id)
    assert second.success is False
    assert second.error_code in {"VALIDATION_ERROR", "INVALID_STATE", "CONFLICT"}


def test_submit_for_review_is_registered_as_a_write_tool():
    from mcp_server.tool_registry import _WRITE_TOOL_PREFIXES

    assert "change_request.submit_for_review" in _WRITE_TOOL_PREFIXES
