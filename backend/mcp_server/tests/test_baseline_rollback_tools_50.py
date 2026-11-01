"""Plan F F4.4 (PR-F11b) — MCP tools for the additive baseline rollback.

Delta: +3 tools (255 -> 258), +0 prefixes (still 41).

Tools pinned here:
  ``baseline.rollback_preview`` — read-only plan (any workspace member, agents too)
  ``baseline.rollback_request`` — opens the CCB change request (write)
  ``baseline.rollback_apply``   — executes the approved rollback (write, humans only)

Requirements:
- ADR-025, REQ-L2-AS-006, REQ-L2-MC-012, SEC-RB-01/08.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from application.baseline_rollback_service import BaselineRollbackService
from application.change_request_service import ChangeRequestService
from application.requirement_service import RequirementService
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, UserRole
from auth_tenancy.services.authentication import AuthenticationService
from baseline.services import build as baseline_build
from mcp_server.protocol_handler import ERROR_CODE_MAP
from mcp_server.tool_registry import ToolRegistry
from mcp_server.tools.baseline import BaselineToolGroup
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, Tenant, User, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


def _make_env(name: str, tier: str = "standard"):
    slug = f"{name}-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name=slug, slug=slug)
    user = User.objects.create(
        username=f"{slug}-user", email=f"{slug}@example.com", tenant=tenant
    )
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=f"{slug}-ws", preset={"name": tier}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    from workflow.services import create_default_workflow

    set_request_tenant(tenant.id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="ccb_approval",
            item_type="ChangeRequest",
            tenant_id=tenant.id,
        )
        create_default_workflow(
            workspace_id=workspace.id,
            preset="standard",
            item_type="Requirement",
            tenant_id=tenant.id,
        )
    finally:
        clear_request_tenant()
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=(ROLE_ADMIN,),
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=workspace.id,
    )
    return tenant, user, workspace, ctx


def _make_requirement(tenant: Tenant, workspace: Workspace, title: str) -> Requirement:
    set_request_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        return Requirement.objects.create(
            tenant=tenant,
            artifact=artifact,
            workspace=workspace,
            uid=f"REQ-{uuid.uuid4().hex[:8]}",
            title=title,
            description="d",
            rationale="because",
            category="functional",
        )
    finally:
        clear_request_tenant()


def _baseline(tenant: Tenant, workspace: Workspace) -> uuid.UUID:
    set_request_tenant(tenant.id)
    try:
        return baseline_build(
            scope="project",
            workspace_id=workspace.id,
            name=f"B-{uuid.uuid4().hex[:6]}",
            tenant_id=tenant.id,
            created_by="f4-4-mcp-test",
        )
    finally:
        clear_request_tenant()


def _changed_baseline(tenant: Tenant, workspace: Workspace, ctx: AuthContext):
    requirement = _make_requirement(tenant, workspace, "Original")
    baseline_id = _baseline(tenant, workspace)
    RequirementService().update_requirement(
        requirement.id, ctx, title="Changed", change_reason="edit after baseline"
    )
    return requirement, baseline_id


def _approve(ctx: AuthContext, cr_id) -> None:
    service = ChangeRequestService()
    service.transition_status(cr_id, "submitted", ctx, change_reason="please review")
    service.transition_status(cr_id, "under_review", ctx, change_reason="picked up")
    service.transition_status(cr_id, "approved", ctx, change_reason="approved")


class TestRollbackToolRegistration:
    def test_three_tools_are_registered(self) -> None:
        registry = ToolRegistry()
        registry._ensure_groups()

        for tool_name in (
            "baseline.rollback_preview",
            "baseline.rollback_request",
            "baseline.rollback_apply",
        ):
            group, error = registry._router.route(tool_name)
            assert error is None
            assert isinstance(group, BaselineToolGroup)

        assert registry._is_write_tool("baseline.rollback_preview") is False
        assert registry._is_write_tool("baseline.rollback_request") is True
        assert registry._is_write_tool("baseline.rollback_apply") is True

    def test_schemas_declare_the_baseline_id(self) -> None:
        schemas = {
            schema["name"]: schema for schema in BaselineToolGroup().get_tool_schemas()
        }

        assert schemas["baseline.rollback_preview"]["inputSchema"]["required"] == ["id"]
        assert "id" in schemas["baseline.rollback_preview"]["inputSchema"]["properties"]
        required = schemas["baseline.rollback_request"]["inputSchema"]["required"]
        assert set(required) == {"id", "change_reason"}
        assert schemas["baseline.rollback_apply"]["inputSchema"]["required"] == [
            "id",
            "change_request_id",
        ]


class TestRollbackToolRoundtrip:
    def test_preview_request_and_apply(self) -> None:
        tenant, _, workspace, ctx = _make_env("rollback-mcp")
        requirement, baseline_id = _changed_baseline(tenant, workspace, ctx)
        group = BaselineToolGroup()

        TenantContext.set_tenant(tenant.id)
        try:
            preview = group._handle_rollback_preview(
                params={"id": str(baseline_id)}, auth_context=ctx, api_key="reqlo_x"
            )
            assert preview.success is True, preview.error_code
            assert preview.data["summary"]["restore"] == 1
            item = next(
                row
                for row in preview.data["items"]
                if row["item_id"] == str(requirement.artifact_id)
            )
            assert item["action"] == "restore"

            requested = group._handle_rollback_request(
                params={"id": str(baseline_id), "change_reason": "restore it"},
                auth_context=ctx,
                api_key="reqlo_x",
            )
            assert requested.success is True, requested.error_code
            assert requested.data["status"] == "draft"
            assert requested.data["affected_items"] == 1
            cr_id = requested.data["change_request_id"]

            _approve(ctx, cr_id)

            applied = group._handle_rollback_apply(
                params={"id": str(baseline_id), "change_request_id": cr_id},
                auth_context=ctx,
                api_key="reqlo_x",
            )
            assert applied.success is True, applied.error_code
            assert applied.data["restored"] == 1
            assert applied.data["change_request_status"] == "implemented"
            requirement.refresh_from_db()
            assert requirement.title == "Original"
        finally:
            TenantContext.clear_tenant()

    def test_preview_on_unknown_baseline_is_not_found(self) -> None:
        tenant, _, _, ctx = _make_env("rollback-mcp-404")
        group = BaselineToolGroup()

        TenantContext.set_tenant(tenant.id)
        try:
            result = group._handle_rollback_preview(
                params={"id": str(uuid.uuid4())},
                auth_context=ctx,
                api_key="reqlo_x",
            )
        finally:
            TenantContext.clear_tenant()

        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    def test_rollback_errors_keep_their_domain_code(self) -> None:
        """A domain refusal is not flattened into VALIDATION_ERROR."""
        tenant, _, workspace, ctx = _make_env("rollback-mcp-codes")
        _, baseline_id = _changed_baseline(tenant, workspace, ctx)
        group = BaselineToolGroup()

        TenantContext.set_tenant(tenant.id)
        try:
            draft = group._handle_rollback_request(
                params={"id": str(baseline_id), "change_reason": "restore"},
                auth_context=ctx,
                api_key="reqlo_x",
            )
            applied = group._handle_rollback_apply(
                params={
                    "id": str(baseline_id),
                    "change_request_id": draft.data["change_request_id"],
                },
                auth_context=ctx,
                api_key="reqlo_x",
            )
        finally:
            TenantContext.clear_tenant()

        assert applied.success is False
        assert applied.error_code == "CONFLICT"
        assert applied.details["code"] == "ROLLBACK_NOT_APPROVED"
        assert "approved" in applied.message


def test_mcp_rollback_apply_agent_key_is_32001() -> None:
    """SEC-RB-08 — executing is human-only, and the refusal is -32001 for a client."""
    tenant, user, workspace, ctx = _make_env("rollback-mcp-agent")
    _, baseline_id = _changed_baseline(tenant, workspace, ctx)
    cr = BaselineRollbackService().request(
        baseline_id, ctx, change_reason="restore the baseline"
    )
    _approve(ctx, cr.id)

    key = AuthenticationService().create_api_key(
        user_id=user.id,
        tenant_id=tenant.id,
        name="f4-4-apply-agent",
        principal_type="agent",
        # ADMIN tier: the refusal below must come from the human-only rule
        # (SEC-RB-08), not from an API-key tier gate that would mask it.
        scope="write",
        workspace_ids=[str(workspace.id)],
        expires_at=timezone.now() + timedelta(days=1),
    )

    result = ToolRegistry().dispatch_request(
        tool_name="baseline.rollback_apply",
        params={"id": str(baseline_id), "change_request_id": str(cr.id)},
        api_key=key.plaintext,
    )

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    assert ERROR_CODE_MAP[result.error_code] == -32001


def test_mcp_rollback_fenced_key_is_32001() -> None:
    """SEC-RB-01 — the API key's workspace fence denies a foreign baseline."""
    tenant, user, _, ctx = _make_env("rollback-mcp-fence")
    set_request_tenant(tenant.id)
    try:
        fenced_workspace = Workspace.objects.create(
            tenant=tenant, name="fence-a", preset={"name": "standard"}
        )
        target_workspace = Workspace.objects.create(
            tenant=tenant, name="fence-b", preset={"name": "standard"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=target_workspace, role=ROLE_ADMIN
        )
        requirement = _make_requirement(tenant, target_workspace, "Original")
        baseline_id = _baseline(tenant, target_workspace)
    finally:
        clear_request_tenant()
    RequirementService().update_requirement(
        requirement.id,
        AuthContext(
            user_id=user.id,
            tenant_id=tenant.id,
            active_roles=(ROLE_ADMIN,),
            auth_method=AuthMethod.BEARER_TOKEN,
            workspace_id=target_workspace.id,
        ),
        title="Changed",
        change_reason="edit after baseline",
    )

    key = AuthenticationService().create_api_key(
        user_id=user.id,
        tenant_id=tenant.id,
        name="f4-4-mcp-fenced",
        principal_type="agent",
        scope="write",
        workspace_ids=[str(fenced_workspace.id)],
        expires_at=timezone.now() + timedelta(days=1),
    )

    result = ToolRegistry().dispatch_request(
        tool_name="baseline.rollback_preview",
        params={"id": str(baseline_id)},
        api_key=key.plaintext,
    )

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    assert ERROR_CODE_MAP[result.error_code] == -32001
