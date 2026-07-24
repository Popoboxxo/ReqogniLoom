"""
Real-DB tests for outdate/reactivate + include_outdated query filtering on the
"own" (non-generic) MCP tool groups (Phase 1 Task 3).

Covers RequirementsToolGroup, ArchitectureToolGroup, McpTestToolGroup and
StakeholderNeedsToolGroup: each gets a create -> outdate -> reactivate
round-trip plus a query test proving include_outdated is respected.

leaf_id : COMP-MC-003, COMP-MC-004, COMP-MC-005, COMP-MC-006
req_id  : REQ-L2-MC-001, REQ-L2-MC-002, REQ-L2-MC-003, REQ-006
"""
from __future__ import annotations

import pytest

from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext
from workflow.models import WorkflowItemState
from workflow.services import create_default_workflow

from mcp_server.tools.requirements import RequirementsToolGroup
from mcp_server.tools.architecture import ArchitectureToolGroup
from mcp_server.tools.tests import TestToolGroup
from mcp_server.tools.needs import StakeholderNeedsToolGroup

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


# ---------------------------------------------------------------------------
# RequirementsToolGroup
# ---------------------------------------------------------------------------


class TestRequirementLifecycleTools:
    def test_outdate_then_reactivate_roundtrip(self):
        from application.requirement_service import RequirementService

        tenant, workspace, ctx = _make_tenant_workspace_ctx("req-mcp-lifecycle")
        _ensure_workflow(tenant, workspace, "standard", "Requirement")

        svc = RequirementService()
        req = svc.create_requirement(workspace_id=workspace.id, title="R1", ctx=ctx)
        group = RequirementsToolGroup(service=svc)

        result = group._handle_outdate(
            params={"id": str(req.id), "reason": "obsolete"},
            auth_context=ctx,
            api_key="reqlo_x",
        )
        assert result.success is True
        assert result.data == {"id": str(req.id), "status": "outdated"}

        state = WorkflowItemState.objects.get(item_id=req.id, item_type="Requirement")
        assert state.current_state == "outdated"

        result2 = group._handle_reactivate(
            params={"id": str(req.id)}, auth_context=ctx, api_key="reqlo_x"
        )
        assert result2.success is True
        assert result2.data["id"] == str(req.id)
        assert result2.data["status"] != "outdated"

    def test_outdate_not_found_returns_error(self):
        from application.requirement_service import RequirementService

        _, _, ctx = _make_tenant_workspace_ctx("req-mcp-notfound")
        group = RequirementsToolGroup(service=RequirementService())

        result = group._handle_outdate(
            params={"id": "00000000-0000-0000-0000-000000009999"},
            auth_context=ctx,
            api_key="reqlo_x",
        )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    def test_query_include_outdated_filters(self):
        from application.requirement_service import RequirementService

        tenant, workspace, ctx = _make_tenant_workspace_ctx("req-mcp-query")
        _ensure_workflow(tenant, workspace, "standard", "Requirement")

        svc = RequirementService()
        kept = svc.create_requirement(workspace_id=workspace.id, title="Kept", ctx=ctx)
        deleted = svc.create_requirement(workspace_id=workspace.id, title="Deleted", ctx=ctx)

        group = RequirementsToolGroup(service=svc)
        group._handle_outdate(params={"id": str(deleted.id)}, auth_context=ctx, api_key="x")

        result = group._handle_query(
            params={"workspace_id": str(workspace.id)}, auth_context=ctx, api_key="x"
        )
        ids = {r["id"] for r in result.data["requirements"]}
        assert str(kept.id) in ids
        assert str(deleted.id) not in ids

        result_incl = group._handle_query(
            params={"workspace_id": str(workspace.id), "include_outdated": True},
            auth_context=ctx,
            api_key="x",
        )
        ids_incl = {r["id"] for r in result_incl.data["requirements"]}
        assert str(deleted.id) in ids_incl


# ---------------------------------------------------------------------------
# ArchitectureToolGroup
# ---------------------------------------------------------------------------


class TestArchitectureLifecycleTools:
    def test_outdate_then_reactivate_roundtrip(self):
        from application.architecture_service import ArchitectureService

        tenant, workspace, ctx = _make_tenant_workspace_ctx("arch-mcp-lifecycle")
        _ensure_workflow(tenant, workspace, "architecture_default", "ArchitectureElement")

        svc = ArchitectureService()
        el = svc.create_architecture_element(
            workspace_id=workspace.id, title="El1", ctx=ctx
        )
        group = ArchitectureToolGroup(service=svc)

        result = group._handle_outdate(
            params={"id": str(el.id), "reason": "obsolete"},
            auth_context=ctx,
            api_key="reqlo_x",
        )
        assert result.success is True
        assert result.data == {"id": str(el.id), "status": "outdated"}

        state = WorkflowItemState.objects.get(
            item_id=el.id, item_type="ArchitectureElement"
        )
        assert state.current_state == "outdated"

        result2 = group._handle_reactivate(
            params={"id": str(el.id)}, auth_context=ctx, api_key="reqlo_x"
        )
        assert result2.success is True
        assert result2.data["id"] == str(el.id)
        assert result2.data["status"] != "outdated"

    def test_outdate_not_found_returns_error(self):
        from application.architecture_service import ArchitectureService

        _, _, ctx = _make_tenant_workspace_ctx("arch-mcp-notfound")
        group = ArchitectureToolGroup(service=ArchitectureService())

        result = group._handle_outdate(
            params={"id": "00000000-0000-0000-0000-000000009999"},
            auth_context=ctx,
            api_key="reqlo_x",
        )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    def test_query_include_outdated_filters(self):
        from application.architecture_service import ArchitectureService

        tenant, workspace, ctx = _make_tenant_workspace_ctx("arch-mcp-query")
        _ensure_workflow(tenant, workspace, "architecture_default", "ArchitectureElement")

        svc = ArchitectureService()
        kept = svc.create_architecture_element(
            workspace_id=workspace.id, title="Kept", ctx=ctx
        )
        # I5 invariant: only one root per workspace — attach the second
        # element under the first instead of making it a second root.
        deleted = svc.create_architecture_element(
            workspace_id=workspace.id, title="Deleted", ctx=ctx, parent_id=kept.id
        )

        group = ArchitectureToolGroup(service=svc)
        group._handle_outdate(params={"id": str(deleted.id)}, auth_context=ctx, api_key="x")

        result = group._handle_query(
            params={"workspace_id": str(workspace.id)}, auth_context=ctx, api_key="x"
        )
        ids = {r["id"] for r in result.data["architecture_elements"]}
        assert str(kept.id) in ids
        assert str(deleted.id) not in ids

        result_incl = group._handle_query(
            params={"workspace_id": str(workspace.id), "include_outdated": True},
            auth_context=ctx,
            api_key="x",
        )
        ids_incl = {r["id"] for r in result_incl.data["architecture_elements"]}
        assert str(deleted.id) in ids_incl


# ---------------------------------------------------------------------------
# TestToolGroup (McpTestToolGroup)
# ---------------------------------------------------------------------------


class TestTestCaseLifecycleTools:
    def test_outdate_then_reactivate_roundtrip(self):
        from application.test_service import TestService

        tenant, workspace, ctx = _make_tenant_workspace_ctx("tc-mcp-lifecycle")
        _ensure_workflow(tenant, workspace, "testcase_default", "TestCase")

        svc = TestService()
        tc = svc.create_test_case(workspace_id=workspace.id, title="TC1", ctx=ctx)
        group = TestToolGroup(service=svc)

        result = group._handle_outdate(
            params={"id": str(tc.id), "reason": "obsolete"},
            auth_context=ctx,
            api_key="reqlo_x",
        )
        assert result.success is True
        assert result.data == {"id": str(tc.id), "status": "outdated"}

        state = WorkflowItemState.objects.get(item_id=tc.id, item_type="TestCase")
        assert state.current_state == "outdated"

        result2 = group._handle_reactivate(
            params={"id": str(tc.id)}, auth_context=ctx, api_key="reqlo_x"
        )
        assert result2.success is True
        assert result2.data["id"] == str(tc.id)
        assert result2.data["status"] != "outdated"

    def test_outdate_not_found_returns_error(self):
        from application.test_service import TestService

        _, _, ctx = _make_tenant_workspace_ctx("tc-mcp-notfound")
        group = TestToolGroup(service=TestService())

        result = group._handle_outdate(
            params={"id": "00000000-0000-0000-0000-000000009999"},
            auth_context=ctx,
            api_key="reqlo_x",
        )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    def test_query_include_outdated_filters(self):
        from application.test_service import TestService

        tenant, workspace, ctx = _make_tenant_workspace_ctx("tc-mcp-query")
        _ensure_workflow(tenant, workspace, "testcase_default", "TestCase")

        svc = TestService()
        kept = svc.create_test_case(workspace_id=workspace.id, title="Kept", ctx=ctx)
        deleted = svc.create_test_case(workspace_id=workspace.id, title="Deleted", ctx=ctx)

        group = TestToolGroup(service=svc)
        group._handle_outdate(params={"id": str(deleted.id)}, auth_context=ctx, api_key="x")

        result = group._handle_query(
            params={"workspace_id": str(workspace.id)}, auth_context=ctx, api_key="x"
        )
        ids = {r["id"] for r in result.data["test_cases"]}
        assert str(kept.id) in ids
        assert str(deleted.id) not in ids

        result_incl = group._handle_query(
            params={"workspace_id": str(workspace.id), "include_outdated": True},
            auth_context=ctx,
            api_key="x",
        )
        ids_incl = {r["id"] for r in result_incl.data["test_cases"]}
        assert str(deleted.id) in ids_incl


# ---------------------------------------------------------------------------
# StakeholderNeedsToolGroup
# ---------------------------------------------------------------------------


class TestStakeholderNeedLifecycleTools:
    def test_outdate_then_reactivate_roundtrip(self):
        from application.stakeholder_need_service import StakeholderNeedService

        tenant, workspace, ctx = _make_tenant_workspace_ctx("need-mcp-lifecycle")
        _ensure_workflow(tenant, workspace, "need_default", "StakeholderNeed")

        svc = StakeholderNeedService(preset_policy_service=None)
        need = svc.create(ctx=ctx, workspace_id=workspace.id, title="N1")
        group = StakeholderNeedsToolGroup(service=svc)

        result = group._handle_outdate(
            params={"id": str(need.id), "reason": "obsolete"},
            auth_context=ctx,
            api_key="reqlo_x",
        )
        assert result.success is True
        assert result.data == {"id": str(need.id), "status": "outdated"}

        state = WorkflowItemState.objects.get(
            item_id=need.id, item_type="StakeholderNeed"
        )
        assert state.current_state == "outdated"

        result2 = group._handle_reactivate(
            params={"id": str(need.id)}, auth_context=ctx, api_key="reqlo_x"
        )
        assert result2.success is True
        assert result2.data["id"] == str(need.id)
        assert result2.data["status"] != "outdated"

    def test_outdate_not_found_returns_error(self):
        from application.stakeholder_need_service import StakeholderNeedService

        tenant, _, ctx = _make_tenant_workspace_ctx("need-mcp-notfound")
        group = StakeholderNeedsToolGroup(
            service=StakeholderNeedService(preset_policy_service=None)
        )

        # StakeholderNeedService.get() relies on a thread-local TenantContext
        # that, in production, mcp_server.tool_registry sets before dispatch
        # (unlike the other 3 services, whose get_*() methods set it
        # themselves). Set it explicitly here since this test calls the
        # handler directly, bypassing the registry.
        TenantContext.set_tenant(tenant.id)
        try:
            result = group._handle_outdate(
                params={"id": "00000000-0000-0000-0000-000000009999"},
                auth_context=ctx,
                api_key="reqlo_x",
            )
        finally:
            TenantContext.clear_tenant()
        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    def test_query_include_outdated_filters(self):
        """needs.query already forwards its (pre-existing) ``include_deleted``
        param to StakeholderNeedService.list_by_workspace — this test just
        confirms the .outdate tool's soft-delete is respected end-to-end."""
        from application.stakeholder_need_service import StakeholderNeedService

        tenant, workspace, ctx = _make_tenant_workspace_ctx("need-mcp-query")
        _ensure_workflow(tenant, workspace, "need_default", "StakeholderNeed")

        svc = StakeholderNeedService(preset_policy_service=None)
        kept = svc.create(ctx=ctx, workspace_id=workspace.id, title="Kept")
        deleted = svc.create(ctx=ctx, workspace_id=workspace.id, title="Deleted")

        group = StakeholderNeedsToolGroup(service=svc)
        group._handle_outdate(params={"id": str(deleted.id)}, auth_context=ctx, api_key="x")

        result = group._handle_query(
            params={"workspace_id": str(workspace.id)}, auth_context=ctx, api_key="x"
        )
        ids = {n["id"] for n in result.data["needs"]}
        assert str(kept.id) in ids
        assert str(deleted.id) not in ids

        result_incl = group._handle_query(
            params={"workspace_id": str(workspace.id), "include_deleted": True},
            auth_context=ctx,
            api_key="x",
        )
        ids_incl = {n["id"] for n in result_incl.data["needs"]}
        assert str(deleted.id) in ids_incl
