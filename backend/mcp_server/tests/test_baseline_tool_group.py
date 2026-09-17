"""
Real-DB tests for BaselineToolGroup (issue #114).

Covers registration in ToolRegistry (fail-closed RBAC gating for the write
tool `baseline.create` vs the read-only `baseline.list`/`.get`/`.compare`)
plus a create -> list -> get -> compare round-trip against the real
BaselineFacade (application/baseline_facade.py), mirroring
test_diagram_tool_group.py's pattern for other "own" tool groups.

leaf_id : COMP-AS-006 (BaselineFacade), COMP-MC-002 (ToolRegistry)
req_id  : REQ-L1-018, REQ-L2-AS-006, REQ-L2-AS-007, REQ-L2-MC-012
"""
from __future__ import annotations

import pytest

from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext

from mcp_server.tool_registry import ToolRegistry
from mcp_server.tools.baseline import BaselineToolGroup

pytestmark = pytest.mark.django_db


def _make_tenant_workspace_ctx(name: str):
    """Create a Tenant + User + Workspace (standard preset) + AuthContext for *name*."""
    from persistence.models import Tenant, User, Workspace

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
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name=name,
    )
    return tenant, workspace, ctx


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestBaselineToolGroupRegistration:
    def test_baseline_tools_registered_in_registry(self):
        registry = ToolRegistry()
        registry._ensure_groups()

        group, error = registry._router.route("baseline.create")
        assert error is None
        assert isinstance(group, BaselineToolGroup)

        for tool_name in ("baseline.list", "baseline.get", "baseline.compare"):
            group, error = registry._router.route(tool_name)
            assert error is None
            assert isinstance(group, BaselineToolGroup)

    def test_write_tools_require_write_role(self):
        registry = ToolRegistry()
        assert registry._is_write_tool("baseline.create") is True
        assert registry._is_write_tool("baseline.list") is False
        assert registry._is_write_tool("baseline.get") is False
        assert registry._is_write_tool("baseline.compare") is False

    def test_baseline_schemas_exposed(self):
        group = BaselineToolGroup()
        names = {schema["name"] for schema in group.get_tool_schemas()}
        assert names == {
            "baseline.create",
            "baseline.list",
            "baseline.get",
            "baseline.compare",
        }


# ---------------------------------------------------------------------------
# CRUD round-trip
# ---------------------------------------------------------------------------


class TestBaselineToolGroupRoundtrip:
    def test_create_list_get_compare_roundtrip(self):
        tenant, workspace, ctx = _make_tenant_workspace_ctx("baseline-mcp-crud")
        group = BaselineToolGroup()

        TenantContext.set_tenant(tenant.id)
        try:
            create_a = group._handle_create(
                params={
                    "workspace_id": str(workspace.id),
                    "scope": "project",
                    "name": "v1.0-baseline",
                    "description": "first snapshot",
                },
                auth_context=ctx,
                api_key="reqlo_x",
            )
            assert create_a.success is True
            baseline_a_id = create_a.data["baseline_id"]

            create_b = group._handle_create(
                params={
                    "workspace_id": str(workspace.id),
                    "scope": "project",
                    "name": "v2.0-baseline",
                    "description": "second snapshot",
                },
                auth_context=ctx,
                api_key="reqlo_x",
            )
            assert create_b.success is True
            baseline_b_id = create_b.data["baseline_id"]

            list_result = group._handle_list(
                params={"workspace_id": str(workspace.id)},
                auth_context=ctx,
                api_key="reqlo_x",
            )
            assert list_result.success is True
            assert list_result.data["count"] == 2
            names = {b["name"] for b in list_result.data["baselines"]}
            assert names == {"v1.0-baseline", "v2.0-baseline"}

            get_result = group._handle_get(
                params={"id": baseline_a_id}, auth_context=ctx, api_key="reqlo_x"
            )
            assert get_result.success is True
            assert get_result.data["baseline"]["name"] == "v1.0-baseline"
            assert get_result.data["baseline"]["scope"] == "project"
            assert "entries" in get_result.data["baseline"]

            compare_result = group._handle_compare(
                params={
                    "baseline_a_id": baseline_a_id,
                    "baseline_b_id": baseline_b_id,
                },
                auth_context=ctx,
                api_key="reqlo_x",
            )
            assert compare_result.success is True
            assert "diff" in compare_result.data
        finally:
            TenantContext.clear_tenant()

    def test_create_duplicate_name_returns_validation_error(self):
        tenant, workspace, ctx = _make_tenant_workspace_ctx("baseline-mcp-dup")
        group = BaselineToolGroup()

        TenantContext.set_tenant(tenant.id)
        try:
            first = group._handle_create(
                params={
                    "workspace_id": str(workspace.id),
                    "scope": "project",
                    "name": "dup-name",
                },
                auth_context=ctx,
                api_key="reqlo_x",
            )
            assert first.success is True

            second = group._handle_create(
                params={
                    "workspace_id": str(workspace.id),
                    "scope": "project",
                    "name": "dup-name",
                },
                auth_context=ctx,
                api_key="reqlo_x",
            )
        finally:
            TenantContext.clear_tenant()

        assert second.success is False
        assert second.error_code == "VALIDATION_ERROR"

    def test_create_document_scope_without_document_id_returns_validation_error(self):
        """GH-715: scope='document' without document_id must be a clean
        VALIDATION_ERROR, never an internal-error-wrapped ValueError."""
        tenant, workspace, ctx = _make_tenant_workspace_ctx("baseline-mcp-docscope")
        group = BaselineToolGroup()

        TenantContext.set_tenant(tenant.id)
        try:
            result = group._handle_create(
                params={
                    "workspace_id": str(workspace.id),
                    "scope": "document",
                    "name": "doc-baseline-no-id",
                },
                auth_context=ctx,
                api_key="reqlo_x",
            )
        finally:
            TenantContext.clear_tenant()

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        assert "document_id is required" in result.message
        assert "internal error" not in result.message

    def test_create_document_scope_with_document_id_succeeds(self):
        """GH-715 success path: scope='document' WITH a valid document_id
        actually creates the baseline and evaluates the gate correctly."""
        tenant, workspace, ctx = _make_tenant_workspace_ctx("baseline-mcp-docscope-ok")
        group = BaselineToolGroup()

        TenantContext.set_tenant(tenant.id)
        try:
            from persistence.models import Artifact

            artifact = Artifact.objects.create(
                tenant=tenant,
                workspace=workspace,
                artifact_type="Requirement",
            )

            result = group._handle_create(
                params={
                    "workspace_id": str(workspace.id),
                    "scope": "document",
                    "name": "doc-baseline-with-id",
                    "document_id": str(artifact.id),
                },
                auth_context=ctx,
                api_key="reqlo_x",
            )
        finally:
            TenantContext.clear_tenant()

        assert result.success is True
        assert "baseline_id" in result.data

    def test_get_not_found_returns_error(self):
        tenant, _, ctx = _make_tenant_workspace_ctx("baseline-mcp-notfound")
        group = BaselineToolGroup()

        TenantContext.set_tenant(tenant.id)
        try:
            result = group._handle_get(
                params={"id": "00000000-0000-0000-0000-000000009999"},
                auth_context=ctx,
                api_key="reqlo_x",
            )
        finally:
            TenantContext.clear_tenant()

        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    def test_create_denied_for_viewer(self):
        tenant, workspace, ctx = _make_tenant_workspace_ctx("baseline-mcp-viewer")
        viewer_ctx = AuthContext(
            user_id=ctx.user_id,
            tenant_id=ctx.tenant_id,
            active_roles=("viewer",),
            auth_method="test",
            api_key_id=None,
            tenant_name=ctx.tenant_name,
        )
        group = BaselineToolGroup()

        TenantContext.set_tenant(tenant.id)
        try:
            result = group._handle_create(
                params={
                    "workspace_id": str(workspace.id),
                    "scope": "project",
                    "name": "viewer-denied",
                },
                auth_context=viewer_ctx,
                api_key="reqlo_x",
            )
        finally:
            TenantContext.clear_tenant()

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# Per-blocker waivers (GH-821)
# ---------------------------------------------------------------------------


def _broken_extended_workspace_ctx(name: str):
    """Tenant + extended Workspace + admin ctx, with one real TRACE-P1 blocker."""
    from persistence.models import Artifact, Requirement, Tenant, User, Workspace

    tenant = Tenant.objects.create(name=name, slug=name)
    user = User.objects.create(
        username=f"{name}-user", email=f"{name}@example.com", tenant=tenant
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=f"{name}-ws", preset={"name": "extended"}
        )
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="requirement"
        )
        Requirement.objects.create(
            tenant=tenant, artifact=artifact, title="Orphan requirement"
        )
    finally:
        TenantContext.clear_tenant()
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method="test",
        api_key_id=None,
        tenant_name=name,
    )
    return tenant, workspace, ctx


class TestBaselineToolGroupWaivers:
    """GH-821: ``baseline.create`` is the per-finding waiver surface for agents.

    No parallel MCP tool was added — the existing create tool carries
    ``waived_findings``, so an agent that hit ``SE_AUDITOR_BLOCKED`` can accept
    individual findings the same way it creates the baseline.
    """

    @staticmethod
    def _reported_findings(workspace, ctx):
        from application.audit_service import AuditService
        from traceability.audit import AuditScope

        findings = AuditService().blocking_findings(
            workspace.id, ctx, scopes=[AuditScope("project")]
        )
        assert findings, "expected the real auditor to report blockers"
        return findings

    def test_waived_findings_create_the_baseline(self):
        tenant, workspace, ctx = _broken_extended_workspace_ctx("baseline-mcp-waive")
        group = BaselineToolGroup()

        TenantContext.set_tenant(tenant.id)
        try:
            findings = self._reported_findings(workspace, ctx)
            result = group._handle_create(
                params={
                    "workspace_id": str(workspace.id),
                    "scope": "project",
                    "name": "gh821-mcp-waived",
                    "waived_findings": [
                        {
                            "rule_id": finding.rule_id,
                            "artifact_ids": list(finding.artifact_ids),
                            "reason": (
                                f"Accepted deviation for {finding.rule_id} via the "
                                "MCP surface."
                            ),
                        }
                        for finding in findings
                    ],
                },
                auth_context=ctx,
                api_key="reqlo_x",
            )

            from baseline.models import BaselineGateWaiver

            rows = BaselineGateWaiver.unscoped.filter(workspace_id=workspace.id)
            row_count = rows.count()
        finally:
            TenantContext.clear_tenant()

        assert result.success is True, result.message
        assert "baseline_id" in result.data
        assert row_count == len(findings)

    def test_malformed_waiver_payload_is_a_validation_error(self):
        """A bad payload must not surface as an internal error (no leakage)."""
        tenant, workspace, ctx = _broken_extended_workspace_ctx("baseline-mcp-badwaive")
        group = BaselineToolGroup()

        TenantContext.set_tenant(tenant.id)
        try:
            result = group._handle_create(
                params={
                    "workspace_id": str(workspace.id),
                    "scope": "project",
                    "name": "gh821-mcp-bad",
                    "waived_findings": "TRACE-P1",
                },
                auth_context=ctx,
                api_key="reqlo_x",
            )
        finally:
            TenantContext.clear_tenant()

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        assert "waived_findings" in result.message
        assert "internal error" not in result.message

    def test_editor_waiver_is_denied(self):
        tenant, workspace, ctx = _broken_extended_workspace_ctx("baseline-mcp-waive-rbac")
        editor_ctx = AuthContext(
            user_id=ctx.user_id,
            tenant_id=ctx.tenant_id,
            active_roles=("editor",),
            auth_method="test",
            api_key_id=None,
            tenant_name=ctx.tenant_name,
        )
        group = BaselineToolGroup()

        TenantContext.set_tenant(tenant.id)
        try:
            findings = self._reported_findings(workspace, editor_ctx)
            result = group._handle_create(
                params={
                    "workspace_id": str(workspace.id),
                    "scope": "project",
                    "name": "gh821-mcp-editor",
                    "waived_findings": [
                        {
                            "rule_id": finding.rule_id,
                            "artifact_ids": list(finding.artifact_ids),
                            "reason": "Editor attempt at accepting a deviation.",
                        }
                        for finding in findings
                    ],
                },
                auth_context=editor_ctx,
                api_key="reqlo_x",
            )
        finally:
            TenantContext.clear_tenant()

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"



__all__: list[str] = []
