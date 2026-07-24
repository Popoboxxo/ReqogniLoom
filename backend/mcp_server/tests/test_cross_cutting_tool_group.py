"""
Real-DB tests for CrossCuttingToolGroup.workspace.get_context (Phase 2 Task 1).

Covers the new ``depth``/``include_outdated``/``role`` params and the
``_entity_counts`` / ``_get_context_token_budget`` helpers.

leaf_id : COMP-MC-006
req_id  : REQ-L2-MC-004
"""
from __future__ import annotations

import pytest

from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db


def _make_tenant_workspace_ctx(name: str):
    """Create a Tenant + User + Workspace + AuthContext triple for *name*."""
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name=name, slug=name)
    user = User.objects.create(
        username=f"{name}-user", email=f"{name}@example.com", tenant=tenant
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name=f"{name}-ws")
    finally:
        TenantContext.clear_tenant()
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name=name,
    )
    return tenant, workspace, ctx


def _ensure_workflow(tenant, workspace, preset: str, item_type: str) -> None:
    TenantContext.set_tenant(tenant.id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset=preset,
            item_type=item_type,
            tenant_id=tenant.id,
        )
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def tenant_workspace_ctx():
    return _make_tenant_workspace_ctx("cross-cutting-ctx")


@pytest.fixture
def auth_ctx(tenant_workspace_ctx):
    _, _, ctx = tenant_workspace_ctx
    return ctx


@pytest.fixture
def workspace_with_data(tenant_workspace_ctx):
    """A workspace with a provisioned Requirement workflow + one active Requirement."""
    from application.requirement_service import RequirementService

    tenant, workspace, ctx = tenant_workspace_ctx
    _ensure_workflow(tenant, workspace, "standard", "Requirement")

    svc = RequirementService()
    svc.create_requirement(workspace_id=workspace.id, title="Active Req", ctx=ctx)

    return workspace.id, tenant.id


@pytest.fixture
def workspace_with_outdated_requirement(tenant_workspace_ctx):
    """A workspace with one active + one outdate()'d Requirement."""
    from application.requirement_service import RequirementService
    from mcp_server.tools.requirements import RequirementsToolGroup

    tenant, workspace, ctx = tenant_workspace_ctx
    _ensure_workflow(tenant, workspace, "standard", "Requirement")

    svc = RequirementService()
    svc.create_requirement(workspace_id=workspace.id, title="Kept", ctx=ctx)
    outdated_req = svc.create_requirement(workspace_id=workspace.id, title="Outdated", ctx=ctx)

    group = RequirementsToolGroup(service=svc)
    result = group._handle_outdate(
        params={"id": str(outdated_req.id), "reason": "obsolete"},
        auth_context=ctx,
        api_key="x",
    )
    assert result.success is True

    return workspace.id, tenant.id, outdated_req.id


@pytest.mark.django_db
def test_get_context_summary_depth_returns_entity_counts(workspace_with_data, auth_ctx):
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    workspace_id, tenant_id = workspace_with_data
    group = CrossCuttingToolGroup()
    result = group.execute_tool(
        "workspace.get_context",
        params={"workspace_id": str(workspace_id), "depth": "summary"},
        auth_context=auth_ctx,
        api_key="",
    )

    assert result.success is True
    ctx = result.data["workspace_context"]
    assert ctx["requirements"]["total"] >= 1
    assert "architecture" in ctx
    assert "tests" in ctx
    assert "risks" in ctx


@pytest.mark.django_db
def test_get_context_excludes_outdated_by_default(workspace_with_outdated_requirement, auth_ctx):
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    workspace_id, tenant_id, outdated_req_id = workspace_with_outdated_requirement
    group = CrossCuttingToolGroup()

    result = group.execute_tool(
        "workspace.get_context",
        params={"workspace_id": str(workspace_id), "depth": "summary"},
        auth_context=auth_ctx, api_key="",
    )
    assert result.data["workspace_context"]["requirements"]["outdated"] == 1
    # active count must not include the outdated one
    active_only = result.data["workspace_context"]["requirements"]["active"]

    result_incl = group.execute_tool(
        "workspace.get_context",
        params={"workspace_id": str(workspace_id), "depth": "summary", "include_outdated": True},
        auth_context=auth_ctx, api_key="",
    )
    assert result_incl.data["workspace_context"]["requirements"]["total"] == active_only + 1


@pytest.mark.django_db
def test_get_context_role_is_label_only_does_not_filter_data(workspace_with_data, auth_ctx):
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    workspace_id, tenant_id = workspace_with_data
    group = CrossCuttingToolGroup()

    result_dev = group.execute_tool(
        "workspace.get_context",
        params={"workspace_id": str(workspace_id), "depth": "summary", "role": "developer"},
        auth_context=auth_ctx, api_key="",
    )
    result_tester = group.execute_tool(
        "workspace.get_context",
        params={"workspace_id": str(workspace_id), "depth": "summary", "role": "tester"},
        auth_context=auth_ctx, api_key="",
    )
    # role must not change which counts come back
    assert result_dev.data["workspace_context"]["requirements"] == result_tester.data["workspace_context"]["requirements"]
    # role is echoed back as a label
    assert result_dev.data["workspace_context"]["role"] == "developer"
    assert result_tester.data["workspace_context"]["role"] == "tester"


@pytest.mark.django_db
def test_get_context_invalid_depth_returns_validation_error(workspace_with_data, auth_ctx):
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    workspace_id, _ = workspace_with_data
    group = CrossCuttingToolGroup()

    result = group.execute_tool(
        "workspace.get_context",
        params={"workspace_id": str(workspace_id), "depth": "invalid"},
        auth_context=auth_ctx, api_key="",
    )
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_get_context_token_budget_defaults():
    from mcp_server.tools.cross_cutting import _get_context_token_budget

    class _FakeWorkspace:
        ai_prompts = None

    ws = _FakeWorkspace()
    assert _get_context_token_budget(ws, "summary") == 300
    assert _get_context_token_budget(ws, "normal") == 2000
    assert _get_context_token_budget(ws, "full") is None


def test_get_context_token_budget_workspace_override():
    from mcp_server.tools.cross_cutting import _get_context_token_budget

    class _FakeWorkspace:
        ai_prompts = {"context_token_budgets": {"summary": 500}}

    ws = _FakeWorkspace()
    assert _get_context_token_budget(ws, "summary") == 500
    # non-overridden depth still falls back to the default
    assert _get_context_token_budget(ws, "normal") == 2000


@pytest.mark.django_db
def test_get_context_test_pass_count_ignores_null_executed_at_placeholder(tenant_workspace_ctx, auth_ctx):
    """Test that most-recent TestRunResult subquery correctly handles NULL executed_at.

    Regression test for bug where TestRunResult.executed_at NULL placeholder
    (status='not_run') was picked instead of real result with executed_at timestamp
    due to ORDER BY executed_at DESC placing NULLs first on PostgreSQL.

    Verifies fix using F("executed_at").desc(nulls_last=True).
    """
    from datetime import datetime, timezone
    from persistence.models import Artifact, TestCase, TestRun, TestRunResult, Workspace
    from application.test_service import TestService

    tenant, workspace, ctx = tenant_workspace_ctx
    _ensure_workflow(tenant, workspace, "standard", "TestCase")

    # Create a TestCase
    TenantContext.set_tenant(tenant.id)
    try:
        tc_service = TestService()
        test_case = tc_service.create_test_case(
            workspace_id=workspace.id,
            title="Test with Placeholder Result",
            ctx=ctx,
        )
        test_case_id = test_case.id

        # Create a TestRun
        test_run = TestRun.objects.create(
            workspace_id=workspace.id,
            name="Test Run 1",
            created_by_id=ctx.user_id,
        )

        # Create placeholder TestRunResult (status='not_run', executed_at=NULL)
        # This mimics what create_test_run does initially
        placeholder = TestRunResult.objects.create(
            test_run=test_run,
            test_case_id=test_case_id,
            status="not_run",
            executed_at=None,
        )

        # Create real passed TestRunResult with timestamp (comes later)
        real_result = TestRunResult.objects.create(
            test_run=test_run,
            test_case_id=test_case_id,
            status="passed",
            executed_at=datetime.now(timezone.utc),
        )

    finally:
        TenantContext.clear_tenant()

    # Call workspace.get_context with depth that includes test counts
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    group = CrossCuttingToolGroup()
    result = group.execute_tool(
        "workspace.get_context",
        params={"workspace_id": str(workspace.id), "depth": "summary"},
        auth_context=ctx,
        api_key="",
    )

    assert result.success is True
    ctx_data = result.data["workspace_context"]

    # Verify that the passed test is correctly counted
    # (should be 1 for "pass", not 0 — the NULL placeholder should be ignored)
    assert ctx_data["tests"]["pass"] == 1, (
        f"Expected pass count=1 (real result), got {ctx_data['tests']['pass']}. "
        "Subquery may have picked NULL placeholder instead of real result."
    )
    # The placeholder is not a "fail", so fail count should remain 0
    assert ctx_data["tests"]["fail"] == 0
