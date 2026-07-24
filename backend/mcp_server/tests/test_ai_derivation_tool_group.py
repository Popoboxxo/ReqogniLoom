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

_API_KEY = "reqlo_testkey_ai"


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


# ---------------------------------------------------------------------------
# Phase 3 (REQ-L2-AI-003) — mode="write" / policy, and the RBAC gate that
# comes with it.
# ---------------------------------------------------------------------------


def test_derive_requirements_preview_mode_unchanged(ai_ctx):
    """mode omitted (defaults to 'preview') returns the identical Phase-2 shape."""
    tenant, ctx, workspace = ai_ctx
    need = _make_need(tenant, workspace, "A need", "desc")

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_requirements_from_need",
        {"need_id": str(need.id), "n": 2},
        ctx,
    )
    result_explicit_preview = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_requirements_from_need",
        {"need_id": str(need.id), "n": 2, "mode": "preview"},
        ctx,
    )

    assert result.success and result_explicit_preview.success
    assert list(result.data.keys()) == ["drafts"]
    assert result.data == result_explicit_preview.data


def test_derive_requirements_write_mode_persists_requirements_and_traces(ai_ctx):
    tenant, ctx, workspace = ai_ctx
    need = _make_need(tenant, workspace, "A need", "desc")

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_requirements_from_need",
        {"need_id": str(need.id), "n": 2, "mode": "write"},
        ctx,
    )

    assert result.success
    written = result.data["written"]
    assert len(written) == 2
    from persistence.models import Requirement, TraceLink

    for entry in written:
        assert entry["status"] == "draft"
        assert Requirement.objects.filter(id=entry["id"]).exists()
        assert TraceLink.objects.filter(id=entry["trace_link_id"]).exists()


def test_suggest_architecture_write_mode_allocates_top_choice(ai_ctx):
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
        {"requirement_id": str(req.id), "mode": "write"},
        ctx,
    )

    assert result.success
    written = result.data["written"]
    assert len(written) == 1
    assert written[0]["target_id"] == str(arch.id)
    from persistence.models import TraceLink

    assert TraceLink.objects.filter(id=written[0]["trace_link_id"]).exists()


def test_decompose_next_level_write_mode_persists_child_requirements(ai_ctx):
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
        {"requirement_id": str(req.id), "mode": "write"},
        ctx,
    )

    assert result.success
    written = result.data["written"]
    assert len(written) >= 1
    from persistence.models import Requirement, TraceLink

    for entry in written:
        assert Requirement.objects.filter(id=entry["id"]).exists()
        assert TraceLink.objects.filter(id=entry["trace_link_id"]).exists()


def test_invalid_mode_is_validation_error(ai_ctx):
    _tenant, ctx, workspace = ai_ctx
    need = _make_need(_tenant, workspace, "A need", "desc")

    result = _exec(
        AiDerivationToolGroup(),
        "ai_derivation.derive_requirements_from_need",
        {"need_id": str(need.id), "mode": "bogus"},
        ctx,
    )

    assert not result.success
    assert result.error_code == "VALIDATION_ERROR"


def test_ai_derivation_tool_names_registered_as_write_tools():
    """All three tools are name-gated as write tools (tool_registry._WRITE_TOOL_PREFIXES),
    complementing the real-RBAC-dispatch proof below.
    """
    from mcp_server.tool_registry import _WRITE_TOOL_PREFIXES

    assert "ai_derivation.derive_requirements_from_need" in _WRITE_TOOL_PREFIXES
    assert (
        "ai_derivation.suggest_architecture_for_requirement" in _WRITE_TOOL_PREFIXES
    )
    assert (
        "ai_derivation.decompose_requirement_next_level" in _WRITE_TOOL_PREFIXES
    )


@pytest.mark.django_db
def test_ai_derivation_write_tools_require_editor_role():
    """A Viewer's mode='write' call is PERMISSION_DENIED via the REAL
    ToolRegistry RBAC gate (not just the mocked ``ai_ctx`` fixture used
    elsewhere in this file) — mirrors test_mcp_rbac_role_matrix.py's pattern.

    The gate is name-based, not mode-aware: this also covers mode='preview'
    calls by the same tool name being denied (documented behaviour change,
    see mcp_server/tools/ai_derivation.py module docstring).
    """
    import uuid
    from unittest.mock import MagicMock

    from auth_tenancy.models import ROLE_VIEWER, UserRole
    from auth_tenancy.services.authentication import AuthenticationService
    from mcp_server.protocol_handler import ToolResult
    from mcp_server.tool_registry import ToolRegistry
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.models import Tenant, User, Workspace as PersistenceWorkspace

    slug = f"mcp-viewer-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name="T-viewer", slug=slug, is_active=True)
    user = User.objects.create(username=f"user-{slug}", email=f"{slug}@t.test", tenant=tenant)
    set_request_tenant(tenant.id)
    try:
        workspace = PersistenceWorkspace.objects.create(tenant=tenant, name="WS-viewer")
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_VIEWER
        )
    finally:
        clear_request_tenant()
    api_key = AuthenticationService().create_api_key(
        user_id=user.id, tenant_id=tenant.id, name="mcp-ai-viewer-key"
    ).plaintext

    registry = ToolRegistry()
    sink = MagicMock()
    sink.execute_tool.return_value = ToolResult.ok({"drafts": []})
    registry.register_groups({"ai_derivation": sink})

    result = registry.dispatch_request(
        tool_name="ai_derivation.derive_requirements_from_need",
        params={"need_id": str(uuid.uuid4()), "workspace_id": str(workspace.id)},
        api_key=api_key,
    )

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    sink.execute_tool.assert_not_called()
