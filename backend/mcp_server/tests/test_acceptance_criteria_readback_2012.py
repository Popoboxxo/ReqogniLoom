"""#2012 — MCP structured acceptance-criteria writes are visible on read-back.

Before the fix, ``requirement.acceptance_criteria.set`` wrote only the JSON
catalogue while ``requirement.get`` projected the legacy free-text column, and
the release gate checked that same (empty) text. A criterion set over MCP was
therefore invisible to readers and blocked release in standard/extended.

These tests drive the real tool group against a real Requirement: the structured
write must materialize the free-text mirror and the read tool must expose both
fields, matching the REST projection.
"""
from __future__ import annotations

import uuid

import pytest

from auth_tenancy.context import AuthContext, AuthMethod


@pytest.fixture
def requirement_env(db):
    from persistence.models import Artifact, Requirement, Tenant, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(name="t-mcp-criteria-2012")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="ws-mcp-criteria-2012")
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    req = Requirement.objects.create(
        tenant=tenant,
        artifact=artifact,
        workspace=workspace,
        title="REQ with criteria",
        description="d",
    )
    ctx = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.SYSTEM,
        workspace_id=workspace.id,
    )
    try:
        yield ctx, req
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_mcp_set_then_get_exposes_both_criteria_stores(requirement_env) -> None:
    from mcp_server.tools.requirements import RequirementsToolGroup

    ctx, req = requirement_env
    group = RequirementsToolGroup()

    set_result = group.execute_tool(
        tool_name="requirement.acceptance_criteria.set",
        params={
            "id": str(req.id),
            "criteria": [
                {"text": "MCP criterion one", "fulfilled": False},
                {"text": "MCP criterion two", "fulfilled": True},
            ],
        },
        auth_context=ctx,
        api_key="reqlo_test",
    )
    assert set_result.success is True, set_result.message

    get_result = group.execute_tool(
        tool_name="requirement.get",
        params={"id": str(req.id)},
        auth_context=ctx,
        api_key="reqlo_test",
    )
    assert get_result.success is True, get_result.message
    payload = get_result.data["requirement"]

    assert [c["text"] for c in payload["acceptance_criteria_items"]] == [
        "MCP criterion one",
        "MCP criterion two",
    ]
    assert payload["acceptance_criteria"] == "MCP criterion one\nMCP criterion two"
