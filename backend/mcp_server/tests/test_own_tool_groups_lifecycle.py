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
        # Phase 4 (D-3): the tool payload above still reports "outdated" (the
        # MCP wire contract is unchanged), but the soft-delete is now the
        # Artifact flag — the workflow state is deliberately preserved.
        assert state.current_state != "outdated"

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
        # Phase 4 (D-3): the tool payload above still reports "outdated" (the
        # MCP wire contract is unchanged), but the soft-delete is now the
        # Artifact flag — the workflow state is deliberately preserved.
        assert state.current_state != "outdated"

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
# ArchitectureToolGroup — parent_id wiring (architecture.create/update)
# ---------------------------------------------------------------------------


class TestArchitectureParentIdTools:
    """architecture.create/update must forward 'parent_id' to the service,
    exactly matching the REST API's already-existing capability. Covers the
    fix for the MCP layer silently dropping 'parent_id'."""

    def test_create_with_parent_id_attaches_as_child(self):
        from application.architecture_service import ArchitectureService

        tenant, workspace, ctx = _make_tenant_workspace_ctx("arch-mcp-parent-create")
        _ensure_workflow(tenant, workspace, "architecture_default", "ArchitectureElement")

        svc = ArchitectureService()
        group = ArchitectureToolGroup(service=svc)

        root = svc.create_architecture_element(
            workspace_id=workspace.id, title="Root", ctx=ctx
        )

        result = group._handle_create(
            params={
                "workspace_id": str(workspace.id),
                "title": "Child",
                "parent_id": str(root.id),
            },
            auth_context=ctx,
            api_key="reqlo_x",
        )
        assert result.success is True
        child_data = result.data["architecture_element"]
        assert child_data["parent_id"] == str(root.id)

    def test_create_without_parent_id_still_creates_root(self):
        from application.architecture_service import ArchitectureService

        tenant, workspace, ctx = _make_tenant_workspace_ctx("arch-mcp-parent-noparent")
        _ensure_workflow(tenant, workspace, "architecture_default", "ArchitectureElement")

        svc = ArchitectureService()
        group = ArchitectureToolGroup(service=svc)

        result = group._handle_create(
            params={"workspace_id": str(workspace.id), "title": "Root"},
            auth_context=ctx,
            api_key="reqlo_x",
        )
        assert result.success is True
        root_data = result.data["architecture_element"]
        assert root_data["parent_id"] is None

    def test_create_second_root_without_parent_id_rejected_i5(self):
        """Unchanged I5 behaviour: a second root (no parent_id, root already
        exists) must still be rejected after the parent_id fix."""
        from application.architecture_service import ArchitectureService

        tenant, workspace, ctx = _make_tenant_workspace_ctx("arch-mcp-parent-i5")
        _ensure_workflow(tenant, workspace, "architecture_default", "ArchitectureElement")

        svc = ArchitectureService()
        group = ArchitectureToolGroup(service=svc)

        group._handle_create(
            params={"workspace_id": str(workspace.id), "title": "Root1"},
            auth_context=ctx,
            api_key="reqlo_x",
        )

        result = group._handle_create(
            params={"workspace_id": str(workspace.id), "title": "Root2"},
            auth_context=ctx,
            api_key="reqlo_x",
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_update_with_parent_id_reparents_element(self):
        from application.architecture_service import ArchitectureService

        tenant, workspace, ctx = _make_tenant_workspace_ctx("arch-mcp-parent-update")
        _ensure_workflow(tenant, workspace, "architecture_default", "ArchitectureElement")

        svc = ArchitectureService()
        group = ArchitectureToolGroup(service=svc)

        root = svc.create_architecture_element(
            workspace_id=workspace.id, title="Root", ctx=ctx
        )
        other = svc.create_architecture_element(
            workspace_id=workspace.id, title="Other", ctx=ctx, parent_id=root.id
        )
        target_parent = svc.create_architecture_element(
            workspace_id=workspace.id, title="NewParent", ctx=ctx, parent_id=root.id
        )

        result = group._handle_update(
            params={
                "id": str(other.id),
                "data": {
                    "expected_version": other.version,
                    "parent_id": str(target_parent.id),
                },
            },
            auth_context=ctx,
            api_key="reqlo_x",
        )
        assert result.success is True
        assert result.data["architecture_element"]["parent_id"] == str(target_parent.id)


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
        # Phase 4 (D-3): the tool payload above still reports "outdated" (the
        # MCP wire contract is unchanged), but the soft-delete is now the
        # Artifact flag — the workflow state is deliberately preserved.
        assert state.current_state != "outdated"

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

    # ------------------------------------------------------------------
    # test.derive_from_requirement mode="write" (Phase 3, REQ-L2-AI-003)
    # ------------------------------------------------------------------

    def test_derive_from_requirement_preview_mode_unchanged(self):
        """mode omitted (defaults to 'preview') returns the identical Phase-2 shape."""
        from application.requirement_service import RequirementService

        _tenant, workspace, ctx = _make_tenant_workspace_ctx("tc-mcp-derive-preview")
        req = RequirementService().create_requirement(
            workspace_id=workspace.id, title="Req1", ctx=ctx
        )
        group = TestToolGroup()

        result = group._handle_derive_from_requirement(
            params={"requirement_id": str(req.id)}, auth_context=ctx, api_key="reqlo_x"
        )
        result_explicit_preview = group._handle_derive_from_requirement(
            params={"requirement_id": str(req.id), "mode": "preview"},
            auth_context=ctx,
            api_key="reqlo_x",
        )

        assert result.success and result_explicit_preview.success
        # Systemaudit item 11: the preview forwards the service dict
        # verbatim, which now also carries the mock-fallback flag.
        assert set(result.data.keys()) == {
            "draft",
            "requirement_id",
            "is_mock_fallback",
        }
        assert result.data == result_explicit_preview.data

    def test_derive_from_requirement_write_mode_persists_testcase_and_verifies_link(self):
        from application.requirement_service import RequirementService
        from persistence.models import TestCase as TestCaseModel, TraceLink

        _tenant, workspace, ctx = _make_tenant_workspace_ctx("tc-mcp-derive-write")
        req = RequirementService().create_requirement(
            workspace_id=workspace.id, title="Req1", ctx=ctx
        )
        group = TestToolGroup()

        result = group._handle_derive_from_requirement(
            params={"requirement_id": str(req.id), "mode": "write"},
            auth_context=ctx,
            api_key="reqlo_x",
        )

        assert result.success is True
        written = result.data["written"]
        assert written["status"] == "draft"

        tc = TestCaseModel.objects.get(id=written["id"])
        assert tc.steps  # mock provider's structured steps were preserved as-is

        link = TraceLink.objects.get(id=written["trace_link_id"])
        # 'verifies' SE endpoint semantics: TestCase is the source, Requirement
        # the target (traceability.types.SE_LINK_SEMANTICS), matching test.link.
        assert str(link.source_id) == str(tc.artifact_id)
        assert str(link.target_id) == str(req.artifact_id)
        assert link.link_type == "verifies"

    def test_derive_from_requirement_write_mode_not_found(self):
        _tenant, _workspace, ctx = _make_tenant_workspace_ctx("tc-mcp-derive-notfound")
        group = TestToolGroup()

        result = group._handle_derive_from_requirement(
            params={
                "requirement_id": "00000000-0000-0000-0000-000000009999",
                "mode": "write",
            },
            auth_context=ctx,
            api_key="reqlo_x",
        )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    def test_derive_from_requirement_invalid_mode_is_validation_error(self):
        from application.requirement_service import RequirementService

        _tenant, workspace, ctx = _make_tenant_workspace_ctx("tc-mcp-derive-badmode")
        req = RequirementService().create_requirement(
            workspace_id=workspace.id, title="Req1", ctx=ctx
        )
        group = TestToolGroup()

        result = group.execute_tool(
            tool_name="test.derive_from_requirement",
            params={"requirement_id": str(req.id), "mode": "bogus"},
            auth_context=ctx,
            api_key="reqlo_x",
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_derive_from_requirement_is_registered_as_write_tool(self):
        """REQ-L2-MC-007: mode='write' makes this tool capable of mutation, so
        (like the three ai_derivation.* tools, Phase 3) it is now registered
        in tool_registry._WRITE_TOOL_PREFIXES. That RBAC gate is name-based,
        not mode-aware: as of Phase 3 a Viewer can no longer call this tool at
        all — including mode='preview'. This supersedes the pre-Phase-3
        assumption in test_tool_groups.py's
        test_derive_from_requirement_is_not_a_write_tool (updated alongside).
        """
        from mcp_server.tool_registry import _WRITE_TOOL_PREFIXES

        assert "test.derive_from_requirement" in _WRITE_TOOL_PREFIXES


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
        # Phase 4 (D-3): the tool payload above still reports "outdated" (the
        # MCP wire contract is unchanged), but the soft-delete is now the
        # Artifact flag — the workflow state is deliberately preserved.
        assert state.current_state != "outdated"

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
