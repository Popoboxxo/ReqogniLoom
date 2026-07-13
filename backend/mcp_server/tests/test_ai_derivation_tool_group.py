"""
REQ-L2-AI-002 — AiDerivationToolGroup MCP tool tests.

Covers the three derivation tools against the credential-free mock provider,
plus schema advertisement and the invalid-input error paths. No network access.
"""
from __future__ import annotations

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from application.architecture_service import ArchitectureService
from application.requirement_service import RequirementService
from application.trace_link_service import TraceLinkService
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    Artifact,
    StakeholderNeed,
    Tenant,
    User,
    Workspace as PersistenceWorkspace,
)
from persistence.tenancy import TenantContext

from mcp_server.tools.ai_derivation import AiDerivationToolGroup

_API_KEY = "rf_testkey_ai"


def _make_need(tenant, workspace, title, description=""):
    """Create a StakeholderNeed directly via ORM (bypasses event publishing)."""
    artifact = Artifact.objects.create(
        workspace=workspace, artifact_type="StakeholderNeed", tenant_id=tenant.id
    )
    return StakeholderNeed.objects.create(
        artifact=artifact, tenant_id=tenant.id, title=title, description=description
    )


@pytest.fixture
def ai_ctx(db):
    """Tenant + workspace + AuthContext with the TenantContext activated."""
    tenant = Tenant.objects.create(name="MCP AI", slug="mcp-ai", is_active=True)
    user = User.objects.create(username="mcpaiuser", email="mcpai@t.test", tenant=tenant)
    set_request_tenant(tenant.id)
    TenantContext.set_tenant(tenant.id)
    workspace = PersistenceWorkspace.objects.create(tenant=tenant, name="mcp-ai-ws")
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


def _exec(group, tool, params, ctx):
    return group.execute_tool(
        tool_name=tool, params=params, auth_context=ctx, api_key=_API_KEY
    )


def test_derive_requirements_from_need_tool(ai_ctx):
    tenant, ctx, workspace = ai_ctx
    need = _make_need(tenant, workspace, "A need", "desc")

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_requirements_from_need",
        {"need_id": str(need.id), "n": 2},
        ctx,
    )

    assert result.success
    assert len(result.data["drafts"]) == 2
    assert result.data["drafts"][0]["suggested_parent_id"] == str(need.id)


def test_suggest_architecture_tool(ai_ctx):
    _tenant, ctx, workspace = ai_ctx
    req = RequirementService().create_requirement(
        workspace_id=workspace.id, title="req", ctx=ctx
    )
    arch = ArchitectureService().create_architecture_element(
        workspace_id=workspace.id, title="Comp", ctx=ctx
    )

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.suggest_architecture_for_requirement",
        {"requirement_id": str(req.id)},
        ctx,
    )

    assert result.success
    assert result.data["suggested_arch_element_ids"] == [str(arch.id)]


def test_suggest_architecture_already_assigned_is_validation_error(ai_ctx):
    _tenant, ctx, workspace = ai_ctx
    req = RequirementService().create_requirement(
        workspace_id=workspace.id, title="req", ctx=ctx
    )
    arch = ArchitectureService().create_architecture_element(
        workspace_id=workspace.id, title="Comp", ctx=ctx
    )
    TraceLinkService().allocate(
        requirement_id=req.id, architecture_element_id=arch.id, ctx=ctx
    )

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.suggest_architecture_for_requirement",
        {"requirement_id": str(req.id)},
        ctx,
    )

    assert not result.success
    assert result.error_code == "VALIDATION_ERROR"


def test_decompose_next_level_tool(ai_ctx):
    _tenant, ctx, workspace = ai_ctx
    req = RequirementService().create_requirement(
        workspace_id=workspace.id, title="parent", ctx=ctx
    )
    arch = ArchitectureService().create_architecture_element(
        workspace_id=workspace.id, title="Comp", ctx=ctx
    )
    TraceLinkService().allocate(
        requirement_id=req.id, architecture_element_id=arch.id, ctx=ctx
    )

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.decompose_requirement_next_level",
        {"requirement_id": str(req.id)},
        ctx,
    )

    assert result.success
    assert result.data["parent_requirement_id"] == str(req.id)
    assert len(result.data["drafts"]) >= 1


def test_decompose_without_allocation_is_validation_error(ai_ctx):
    _tenant, ctx, workspace = ai_ctx
    req = RequirementService().create_requirement(
        workspace_id=workspace.id, title="parent", ctx=ctx
    )

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.decompose_requirement_next_level",
        {"requirement_id": str(req.id)},
        ctx,
    )

    assert not result.success
    assert result.error_code == "VALIDATION_ERROR"


def test_missing_uuid_is_validation_error(ai_ctx):
    _tenant, ctx, _workspace = ai_ctx

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.suggest_architecture_for_requirement",
        {},
        ctx,
    )

    assert not result.success
    assert result.error_code == "VALIDATION_ERROR"


def test_schema_advertises_three_tools():
    schemas = AiDerivationToolGroup().get_tool_schemas()
    names = {s["name"] for s in schemas}
    assert names == {
        "ai_derivation.derive_requirements_from_need",
        "ai_derivation.suggest_architecture_for_requirement",
        "ai_derivation.decompose_requirement_next_level",
    }
