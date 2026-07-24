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
def test_get_context_normal_depth_returns_item_lists(workspace_with_data, auth_ctx):
    """REQ-L2-MC-004 (Phase 2, Task 2): depth=normal adds per-item lists."""
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    workspace_id, tenant_id = workspace_with_data
    group = CrossCuttingToolGroup()
    result = group.execute_tool(
        "workspace.get_context",
        params={"workspace_id": str(workspace_id), "depth": "normal"},
        auth_context=auth_ctx, api_key="",
    )
    assert result.success is True
    ctx = result.data["workspace_context"]
    assert isinstance(ctx["requirements_list"], list)
    assert ctx["requirements_list"][0].keys() >= {"id", "title", "status", "level"}
    assert isinstance(ctx["architecture_list"], list)
    assert isinstance(ctx["tests_list"], list)


@pytest.fixture
def workspace_with_outdated_architecture_element(tenant_workspace_ctx):
    """A workspace with one active + one outdate()'d ArchitectureElement."""
    from application.architecture_service import ArchitectureService
    from mcp_server.tools.architecture import ArchitectureToolGroup

    tenant, workspace, ctx = tenant_workspace_ctx
    _ensure_workflow(tenant, workspace, "standard", "ArchitectureElement")

    svc = ArchitectureService()
    kept = svc.create_architecture_element(workspace_id=workspace.id, title="Kept", ctx=ctx)
    outdated_el = svc.create_architecture_element(
        workspace_id=workspace.id, title="Outdated", ctx=ctx, parent_id=kept.id
    )

    group = ArchitectureToolGroup(service=svc)
    result = group._handle_outdate(
        params={"id": str(outdated_el.id), "reason": "obsolete"},
        auth_context=ctx,
        api_key="x",
    )
    assert result.success is True

    return workspace.id, tenant.id, kept.id, outdated_el.id


@pytest.mark.django_db
def test_get_context_normal_depth_marks_outdated_architecture_element_status(
    workspace_with_outdated_architecture_element, auth_ctx
):
    """REQ-006 fix: architecture_list ``status`` must reflect the real
    WorkflowItemState-based outdated flag, not the dead
    ``lifecycle_status`` mirror field (which is never written by outdate()).
    """
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    workspace_id, tenant_id, kept_id, outdated_id = workspace_with_outdated_architecture_element
    group = CrossCuttingToolGroup()

    result = group.execute_tool(
        "workspace.get_context",
        params={
            "workspace_id": str(workspace_id),
            "depth": "normal",
            "include_outdated": True,
        },
        auth_context=auth_ctx, api_key="",
    )
    assert result.success is True
    architecture_list = result.data["workspace_context"]["architecture_list"]
    by_id = {str(item["id"]): item for item in architecture_list}

    assert str(outdated_id) in by_id
    assert by_id[str(outdated_id)]["status"] == "outdated"
    assert str(kept_id) in by_id
    assert by_id[str(kept_id)]["status"] == "active"


@pytest.mark.django_db
def test_get_context_summary_depth_omits_item_lists(workspace_with_data, auth_ctx):
    """REQ-L2-MC-004 (Phase 2, Task 2): depth=summary must not compute item lists."""
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    workspace_id, tenant_id = workspace_with_data
    group = CrossCuttingToolGroup()
    result = group.execute_tool(
        "workspace.get_context",
        params={"workspace_id": str(workspace_id), "depth": "summary"},
        auth_context=auth_ctx, api_key="",
    )
    assert result.success is True
    ctx = result.data["workspace_context"]
    assert "requirements_list" not in ctx
    assert "architecture_list" not in ctx
    assert "tests_list" not in ctx


@pytest.fixture
def workspace_with_verified_test_case(tenant_workspace_ctx):
    """A workspace with a Requirement, a TestCase verifying it (via TraceLink
    link_type=verifies), and a second, unlinked TestCase.
    """
    from application.requirement_service import RequirementService
    from application.test_service import TestService
    from application.trace_link_service import TraceLinkService
    from traceability.types import LinkType

    tenant, workspace, ctx = tenant_workspace_ctx
    _ensure_workflow(tenant, workspace, "standard", "Requirement")
    _ensure_workflow(tenant, workspace, "standard", "TestCase")

    req_svc = RequirementService()
    requirement = req_svc.create_requirement(workspace_id=workspace.id, title="Req", ctx=ctx)

    test_svc = TestService()
    linked_test = test_svc.create_test_case(
        workspace_id=workspace.id, title="Linked Test", ctx=ctx
    )
    unlinked_test = test_svc.create_test_case(
        workspace_id=workspace.id, title="Unlinked Test", ctx=ctx
    )

    trace_svc = TraceLinkService()
    trace_svc.create_trace_link(
        source_id=linked_test.artifact_id,
        target_id=requirement.id,
        link_type=LinkType.VERIFIES.value,
        ctx=ctx,
    )

    return workspace.id, tenant.id, requirement.id, linked_test.id, unlinked_test.id


@pytest.mark.django_db
def test_get_context_normal_depth_resolves_linked_req_id_via_verifies_tracelink(
    workspace_with_verified_test_case, auth_ctx
):
    """Regression test: tests_list.linked_req_id must resolve the real
    Requirement ID via the correlated TraceLink(link_type=verifies) subquery
    — not just "is a list".
    """
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    workspace_id, tenant_id, requirement_id, linked_test_id, unlinked_test_id = (
        workspace_with_verified_test_case
    )
    group = CrossCuttingToolGroup()

    result = group.execute_tool(
        "workspace.get_context",
        params={"workspace_id": str(workspace_id), "depth": "normal"},
        auth_context=auth_ctx, api_key="",
    )
    assert result.success is True
    tests_list = result.data["workspace_context"]["tests_list"]
    by_id = {str(item["id"]): item for item in tests_list}

    assert str(linked_test_id) in by_id
    assert by_id[str(linked_test_id)]["linked_req_id"] == requirement_id

    assert str(unlinked_test_id) in by_id
    assert by_id[str(unlinked_test_id)]["linked_req_id"] is None


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


@pytest.mark.django_db
def test_get_context_full_depth_includes_all_fields(
    workspace_with_outdated_requirement, auth_ctx
):
    """REQ-L2-MC-004 (Phase 2, Task 3): depth=full adds recent_changes on top
    of everything depth=normal already returns."""
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    workspace_id, tenant_id, outdated_req_id = workspace_with_outdated_requirement
    group = CrossCuttingToolGroup()
    result = group.execute_tool(
        "workspace.get_context",
        params={"workspace_id": str(workspace_id), "depth": "full"},
        auth_context=auth_ctx, api_key="",
    )

    assert result.success is True
    ctx = result.data["workspace_context"]
    assert isinstance(ctx["requirements_list"], list)
    assert isinstance(ctx["architecture_list"], list)
    assert isinstance(ctx["tests_list"], list)
    assert isinstance(ctx["recent_changes"], list)
    assert len(ctx["recent_changes"]) >= 1

    entry = ctx["recent_changes"][0]
    assert entry.keys() >= {"entity_type", "title", "timestamp"}
    outdate_entries = [e for e in ctx["recent_changes"] if e["entity_type"] == "Requirement"]
    assert any(e["title"] == "Outdated" for e in outdate_entries)


# ---------------------------------------------------------------------------
# context.test_coverage (Phase 2, Task 5)
# ---------------------------------------------------------------------------

@pytest.fixture
def requirement_with_tests(tenant_workspace_ctx):
    """A workspace with a Requirement verified by one TestCase (via TraceLink
    link_type=verifies) and a second, unverified Requirement (a coverage gap).
    """
    from application.requirement_service import RequirementService
    from application.test_service import TestService
    from application.trace_link_service import TraceLinkService
    from traceability.types import LinkType

    tenant, workspace, ctx = tenant_workspace_ctx
    _ensure_workflow(tenant, workspace, "standard", "Requirement")
    _ensure_workflow(tenant, workspace, "standard", "TestCase")

    req_svc = RequirementService()
    requirement = req_svc.create_requirement(workspace_id=workspace.id, title="Req", ctx=ctx)
    gap_requirement = req_svc.create_requirement(
        workspace_id=workspace.id, title="Uncovered Req", ctx=ctx
    )

    test_svc = TestService()
    test_case = test_svc.create_test_case(
        workspace_id=workspace.id, title="Verifying Test", ctx=ctx
    )

    trace_svc = TraceLinkService()
    trace_svc.create_trace_link(
        source_id=test_case.artifact_id,
        target_id=requirement.id,
        link_type=LinkType.VERIFIES.value,
        ctx=ctx,
    )

    return requirement.id, workspace.id, gap_requirement.id


@pytest.mark.django_db
def test_context_test_coverage_returns_test_cases_and_gaps(requirement_with_tests, auth_ctx):
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    req_id, workspace_id, gap_req_id = requirement_with_tests
    group = CrossCuttingToolGroup()
    result = group.execute_tool(
        "context.test_coverage",
        params={"requirement_id": str(req_id)},
        auth_context=auth_ctx, api_key="",
    )
    assert result.success is True
    assert "test_cases" in result.data
    assert "gaps" in result.data  # requirements without any linked test case, per the design spec's "Lücken" wording
    assert len(result.data["test_cases"]) == 1
    assert result.data["gaps"] == []


@pytest.mark.django_db
def test_context_test_coverage_reports_gap_for_uncovered_requirement(
    requirement_with_tests, auth_ctx
):
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    req_id, workspace_id, gap_req_id = requirement_with_tests
    group = CrossCuttingToolGroup()
    result = group.execute_tool(
        "context.test_coverage",
        params={"requirement_id": str(gap_req_id)},
        auth_context=auth_ctx, api_key="",
    )
    assert result.success is True
    assert result.data["test_cases"] == []
    assert result.data["gaps"] == [str(gap_req_id)]


@pytest.mark.django_db
def test_context_test_coverage_requires_requirement_id(auth_ctx):
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    group = CrossCuttingToolGroup()
    result = group.execute_tool(
        "context.test_coverage", params={}, auth_context=auth_ctx, api_key=""
    )
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_context_test_coverage_not_found_for_unknown_requirement(auth_ctx):
    import uuid

    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    group = CrossCuttingToolGroup()
    result = group.execute_tool(
        "context.test_coverage",
        params={"requirement_id": str(uuid.uuid4())},
        auth_context=auth_ctx, api_key="",
    )
    assert result.success is False
    assert result.error_code == "NOT_FOUND"


@pytest.mark.django_db
def test_context_test_coverage_excludes_outdated_test_case_by_default(
    workspace_with_outdated_requirement, auth_ctx
):
    """A verifying TestCase that is outdated must not appear in
    ``test_cases`` unless ``include_outdated=True`` is passed — mirrors the
    ``CoverageCalculator.get_coverage_data(include_outdated=...)`` contract.
    """
    from application.test_service import TestService
    from application.trace_link_service import TraceLinkService
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup
    from mcp_server.tools.tests import McpTestToolGroup
    from traceability.types import LinkType

    workspace_id, tenant_id, outdated_req_id = workspace_with_outdated_requirement

    from persistence.models import Tenant, Workspace

    workspace = Workspace.objects.get(id=workspace_id)
    tenant = Tenant.objects.get(id=tenant_id)
    _ensure_workflow(tenant, workspace, "standard", "TestCase")

    test_svc = TestService()
    test_case = test_svc.create_test_case(
        workspace_id=workspace_id, title="Outdated Test", ctx=auth_ctx
    )
    trace_svc = TraceLinkService()
    trace_svc.create_trace_link(
        source_id=test_case.artifact_id,
        target_id=outdated_req_id,
        link_type=LinkType.VERIFIES.value,
        ctx=auth_ctx,
    )

    tests_group = McpTestToolGroup(service=test_svc)
    outdate_result = tests_group.execute_tool(
        "test.outdate",
        params={"id": str(test_case.id), "reason": "obsolete"},
        auth_context=auth_ctx, api_key="",
    )
    assert outdate_result.success is True

    group = CrossCuttingToolGroup()
    result_default = group.execute_tool(
        "context.test_coverage",
        params={"requirement_id": str(outdated_req_id)},
        auth_context=auth_ctx, api_key="",
    )
    assert result_default.success is True
    assert result_default.data["test_cases"] == []
    assert result_default.data["gaps"] == [str(outdated_req_id)]

    result_incl = group.execute_tool(
        "context.test_coverage",
        params={"requirement_id": str(outdated_req_id), "include_outdated": True},
        auth_context=auth_ctx, api_key="",
    )
    assert result_incl.success is True
    assert len(result_incl.data["test_cases"]) == 1
    assert result_incl.data["gaps"] == []


@pytest.fixture
def workspace_with_many_requirements(tenant_workspace_ctx):
    """A workspace with enough Requirements that a naive summary payload
    would exceed the default ``summary`` token budget (300 tokens)."""
    from application.requirement_service import RequirementService

    tenant, workspace, ctx = tenant_workspace_ctx
    _ensure_workflow(tenant, workspace, "standard", "Requirement")

    svc = RequirementService()
    for i in range(50):
        svc.create_requirement(
            workspace_id=workspace.id,
            title=f"Requirement number {i} with a fairly long descriptive title",
            ctx=ctx,
        )

    return workspace.id, tenant.id


@pytest.mark.django_db
def test_get_context_summary_depth_is_truncated_under_budget(
    workspace_with_many_requirements, auth_ctx
):
    """REQ-L2-MC-004 (Phase 2, Task 3): depth=summary must stay under the
    configured token budget even if the naive payload would exceed it."""
    import json

    from mcp_server.tools.cross_cutting import (
        CrossCuttingToolGroup,
        DEFAULT_CONTEXT_TOKEN_BUDGETS,
    )

    workspace_id, tenant_id = workspace_with_many_requirements
    group = CrossCuttingToolGroup()
    result = group.execute_tool(
        "workspace.get_context",
        params={"workspace_id": str(workspace_id), "depth": "summary"},
        auth_context=auth_ctx, api_key="",
    )

    assert result.success is True
    ctx = result.data["workspace_context"]
    estimated_tokens = len(json.dumps(ctx, default=str)) // 4
    assert estimated_tokens <= DEFAULT_CONTEXT_TOKEN_BUDGETS["summary"]
    # depth=summary never had list keys to begin with — the budget should
    # never raise, just leave the (already small) payload as-is.
    assert ctx["requirements"]["total"] >= 50


@pytest.mark.django_db
def test_workspace_can_override_token_budget(workspace_with_data, auth_ctx):
    """REQ-L2-MC-004 (Phase 2, Task 3): a workspace-level
    ``ai_prompts["context_token_budgets"]`` override must be honoured."""
    import json

    from persistence.models import Workspace
    from persistence.tenancy import TenantContext

    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    workspace_id, tenant_id = workspace_with_data

    TenantContext.set_tenant(tenant_id)
    try:
        workspace = Workspace.objects.get(id=workspace_id)
        workspace.ai_prompts = {"context_token_budgets": {"normal": 1}}
        workspace.save()
    finally:
        TenantContext.clear_tenant()

    group = CrossCuttingToolGroup()
    result = group.execute_tool(
        "workspace.get_context",
        params={"workspace_id": str(workspace_id), "depth": "normal"},
        auth_context=auth_ctx, api_key="",
    )

    assert result.success is True
    ctx = result.data["workspace_context"]
    # Budget of 1 token forces every list key to be dropped.
    assert "requirements_list" not in ctx
    assert "architecture_list" not in ctx
    assert "tests_list" not in ctx


@pytest.mark.django_db
def test_llm_system_prompt_includes_requirements_and_architecture(workspace_with_data, auth_ctx):
    """REQ-L2-MC-004 (Phase 2, Task 4): ``workspace.llm_system_prompt`` renders
    a natural-language system prompt from the same entity data as
    ``workspace.get_context``."""
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    workspace_id, tenant_id = workspace_with_data
    group = CrossCuttingToolGroup()
    result = group.execute_tool(
        "workspace.llm_system_prompt",
        params={"workspace_id": str(workspace_id), "role": "developer"},
        auth_context=auth_ctx, api_key="",
    )

    assert result.success is True
    prompt = result.data["system_prompt"]
    assert isinstance(prompt, str)
    assert "Requirements" in prompt or "requirement" in prompt.lower()


@pytest.mark.django_db
def test_llm_system_prompt_missing_workspace_id_returns_validation_error(auth_ctx):
    """workspace_id is required for workspace.llm_system_prompt."""
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    group = CrossCuttingToolGroup()
    result = group.execute_tool(
        "workspace.llm_system_prompt",
        params={},
        auth_context=auth_ctx, api_key="",
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_llm_system_prompt_unknown_workspace_returns_not_found(auth_ctx):
    """Unknown workspace_id returns NOT_FOUND, not a raw exception."""
    import uuid

    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    group = CrossCuttingToolGroup()
    result = group.execute_tool(
        "workspace.llm_system_prompt",
        params={"workspace_id": str(uuid.uuid4())},
        auth_context=auth_ctx, api_key="",
    )

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


@pytest.mark.django_db
def test_llm_system_prompt_role_is_label_only_does_not_filter_data(workspace_with_data, auth_ctx):
    """REQ-L2-MC-004 (Phase 2, Task 4): ``role`` in workspace.llm_system_prompt
    is echoed as a text label only ("Du bist als {role} unterwegs") and never
    filters the underlying data. The requirements and architecture sections
    must be identical regardless of role."""
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    workspace_id, tenant_id = workspace_with_data
    group = CrossCuttingToolGroup()

    result_dev = group.execute_tool(
        "workspace.llm_system_prompt",
        params={"workspace_id": str(workspace_id), "role": "developer"},
        auth_context=auth_ctx, api_key="",
    )
    result_tester = group.execute_tool(
        "workspace.llm_system_prompt",
        params={"workspace_id": str(workspace_id), "role": "tester"},
        auth_context=auth_ctx, api_key="",
    )

    assert result_dev.success is True
    assert result_tester.success is True

    prompt_dev = result_dev.data["system_prompt"]
    prompt_tester = result_tester.data["system_prompt"]

    # Extract the requirements and architecture sections (everything after the role line)
    # to verify the substantive data is identical
    dev_sections = prompt_dev.split("## Aktive Requirements")[1] if "## Aktive Requirements" in prompt_dev else ""
    tester_sections = prompt_tester.split("## Aktive Requirements")[1] if "## Aktive Requirements" in prompt_tester else ""
    assert dev_sections == tester_sections, "Requirements and architecture sections must be identical"

    # Verify the role label is echoed correctly in each prompt
    assert "Du bist als developer unterwegs" in prompt_dev
    assert "Du bist als tester unterwegs" in prompt_tester
