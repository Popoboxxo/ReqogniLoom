"""
SysEng 2.0 N1 — ArchitectureToolGroup architecture.decompose(_commit) MCP tests.

Exercises the two new tools through the tool group's ``execute_tool`` entry
(bypassing the full auth pipeline, like test_ai_derivation_tool_group.py):
generate returns a draft (no persistence), commit persists it and passes the
SE-Auditor, and the minimal preset blocks the tool (FEATURE_NOT_ENABLED). No
network access — the mock provider answers deterministically.
"""
from __future__ import annotations

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    Artifact,
    ArchitectureElement,
    Requirement,
    Tenant,
    TraceLink,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext
from presets.services import switch_preset
from traceability.types import LinkType

from mcp_server.tools.architecture import ArchitectureToolGroup

_API_KEY = "reqlo_testkey_n1"


@pytest.fixture
def n1_ctx(db):
    tenant = Tenant.objects.create(name="MCP N1", slug="mcp-n1", is_active=True)
    user = User.objects.create(username="mcpn1", email="n1@t.test", tenant=tenant)
    set_request_tenant(tenant.id)
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="mcp-n1-ws")
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )
    try:
        yield tenant, ctx, workspace
    finally:
        TenantContext.clear_tenant()
        clear_request_tenant()


def _seed(tenant, workspace):
    root_art = Artifact.objects.create(
        workspace=workspace, artifact_type="ArchitectureElement", tenant_id=tenant.id
    )
    root = ArchitectureElement.objects.create(
        artifact=root_art, tenant_id=tenant.id, title="Subsystem"
    )
    req_art = Artifact.objects.create(
        workspace=workspace, artifact_type="Requirement", tenant_id=tenant.id
    )
    anchor = Requirement.objects.create(
        artifact=req_art, tenant_id=tenant.id, title="Anchor"
    )
    TraceLink.objects.create(
        tenant=tenant,
        source=anchor.artifact,
        target=root.artifact,
        link_type=LinkType.ALLOCATED_TO.value,
    )
    return root, anchor


def _exec(group, tool, params, ctx):
    return group.execute_tool(
        tool_name=tool, params=params, auth_context=ctx, api_key=_API_KEY
    )


def test_generate_then_commit_roundtrip(n1_ctx):
    tenant, ctx, workspace = n1_ctx
    switch_preset(str(workspace.id), "extended")
    root, _anchor = _seed(tenant, workspace)
    group = ArchitectureToolGroup()

    gen = _exec(
        group,
        "architecture.decompose",
        {"element_id": str(root.id), "max_breadth": 2, "max_depth": 1},
        ctx,
    )
    assert gen.success
    draft = gen.data["draft"]
    assert len(draft["nodes"]) == 2

    commit = _exec(
        group,
        "architecture.decompose_commit",
        {"workspace_id": str(workspace.id), "draft": draft},
        ctx,
    )
    assert commit.success
    assert commit.data["committed"] is True
    assert commit.data["counts"]["elements"] == 2
    assert ArchitectureElement.objects.filter(parent_id=root.id).count() == 2


def test_generate_blocked_in_minimal_preset(n1_ctx):
    tenant, ctx, workspace = n1_ctx
    # fresh workspace is minimal by default
    root, _ = _seed(tenant, workspace)
    result = _exec(
        ArchitectureToolGroup(),
        "architecture.decompose",
        {"element_id": str(root.id)},
        ctx,
    )
    assert not result.success
    assert result.error_code == "FEATURE_NOT_ENABLED"


def test_commit_requires_draft_object(n1_ctx):
    _tenant, ctx, workspace = n1_ctx
    switch_preset(str(workspace.id), "extended")
    result = _exec(
        ArchitectureToolGroup(),
        "architecture.decompose_commit",
        {"workspace_id": str(workspace.id)},
        ctx,
    )
    assert not result.success
    assert result.error_code == "VALIDATION_ERROR"


def test_schema_advertises_decompose_tools():
    names = {s["name"] for s in ArchitectureToolGroup().get_tool_schemas()}
    assert "architecture.decompose" in names
    assert "architecture.decompose_commit" in names
