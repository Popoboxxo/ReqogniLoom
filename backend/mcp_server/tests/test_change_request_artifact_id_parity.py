"""``artifact_id`` parity for ``change_request.*`` MCP tools (#1763 / audit 2026-11-15).

leaf_id : COMP-AS-021, COMP-MC
req_id  : REQ-157

The Inspector's comment/version/trace panels address an entity by its
**Artifact** id, not by the per-type entity id. REST got the field (see
``rest_api/tests/test_artifact_id_parity_1763.py``); ``GenericCrudToolGroup``
builds its payload from the ORM row, so the MCP half should already carry it.
This test pins that, because "it works by accident of ``obj.__dict__``" is
exactly the kind of contract that silently disappears the next time the
generic group switches to a DTO.
"""
from __future__ import annotations

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tools.generic import GenericCrudToolGroup

pytestmark = pytest.mark.django_db

API_KEY = "reqlo-test"


def _tenant_workspace_ctx(name: str):
    """Create a Tenant + User + Workspace + editor/admin AuthContext."""
    from persistence.models import Tenant, User, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(name=name, slug=name)
    user = User.objects.create(
        username=f"{name}-user", email=f"{name}@example.com", tenant=tenant
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=f"{name}-ws", preset={"name": "standard"}
        )
    finally:
        TenantContext.clear_tenant()
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor", "admin"),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )
    return tenant, workspace, ctx


def _stored_artifact_id(tenant_id, cr_id: str):
    from persistence.models import ChangeRequest
    from persistence.tenancy import TenantContext

    TenantContext.set_tenant(tenant_id)
    try:
        return ChangeRequest.objects.get(id=cr_id).artifact_id
    finally:
        TenantContext.clear_tenant()


def test_change_request_read_and_query_carry_the_backing_artifact_id() -> None:
    from application.change_request_service import ChangeRequestService

    tenant, workspace, ctx = _tenant_workspace_ctx("cr-artifact-id")
    group = GenericCrudToolGroup(
        "change_request", ChangeRequestService, item_type="ChangeRequest"
    )

    created = group.execute_tool(
        tool_name="change_request.create",
        params={"workspace_id": str(workspace.id), "title": "CR artifact id parity"},
        auth_context=ctx,
        api_key=API_KEY,
    )
    assert created.success is True, created.message
    cr_id = created.data["data"]["id"]

    stored = _stored_artifact_id(tenant.id, cr_id)
    assert stored is not None, "the service layer must create the backing Artifact"

    read = group.execute_tool(
        tool_name="change_request.read",
        params={"id": cr_id},
        auth_context=ctx,
        api_key=API_KEY,
    )
    assert read.success is True, read.message
    assert read.data["data"]["artifact_id"] == str(stored)

    query = group.execute_tool(
        tool_name="change_request.query",
        params={"workspace_id": str(workspace.id)},
        auth_context=ctx,
        api_key=API_KEY,
    )
    assert query.success is True, query.message
    rows = {row["id"]: row for row in query.data["items"]}
    assert rows[cr_id]["artifact_id"] == str(stored)
