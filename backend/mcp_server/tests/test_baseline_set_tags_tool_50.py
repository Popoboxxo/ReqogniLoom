"""F4.2 — MCP ``baseline.set_tags`` tool (real DB).

Plan F (2026-10-21), F4.2. Delta: +1 tool (254 -> 255), 0 prefixes.

Requirements:
- REQ-L2-AS-006, REQ-L2-MC-012, REQ-L2-PL-010 (fenced API keys).
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from auth_tenancy.context import AuthContext
from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, UserRole
from auth_tenancy.services.authentication import AuthenticationService
from baseline.models import BaselineSnapshot
from mcp_server.protocol_handler import ERROR_CODE_MAP
from mcp_server.tool_registry import ToolRegistry
from mcp_server.tools.baseline import BaselineToolGroup
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


def _make_tenant_workspace_ctx(name: str, tier: str = "standard"):
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
            tenant=tenant, user=user, workspace=workspace, role=ROLE_EDITOR
        )
    finally:
        clear_request_tenant()
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=(ROLE_EDITOR,),
        auth_method="test",
        api_key_id=None,
        tenant_name=slug,
        workspace_id=workspace.id,
    )
    return tenant, user, workspace, ctx


class TestBaselineSetTagsRegistration:
    def test_tool_is_registered_as_write(self) -> None:
        registry = ToolRegistry()
        registry._ensure_groups()

        group, error = registry._router.route("baseline.set_tags")
        assert error is None
        assert isinstance(group, BaselineToolGroup)
        assert registry._is_write_tool("baseline.set_tags") is True

    def test_schema_declares_id_and_tags(self) -> None:
        group = BaselineToolGroup()
        schemas = {s["name"]: s for s in group.get_tool_schemas()}
        schema = schemas["baseline.set_tags"]
        assert schema["inputSchema"]["required"] == ["id"]
        assert set(schema["inputSchema"]["properties"]) >= {"id", "tags"}


class TestBaselineSetTagsRoundtrip:
    def test_create_with_tags_then_set_tags_then_filter(self) -> None:
        tenant, _, workspace, ctx = _make_tenant_workspace_ctx("tag-mcp")
        group = BaselineToolGroup()

        TenantContext.set_tenant(tenant.id)
        try:
            created = group._handle_create(
                params={
                    "workspace_id": str(workspace.id),
                    "scope": "project",
                    "name": "tagged-baseline",
                    "tags": ["Release"],
                },
                auth_context=ctx,
                api_key="reqlo_x",
            )
            assert created.success is True, created.error_code
            baseline_id = created.data["baseline_id"]

            replaced = group._handle_set_tags(
                params={"id": baseline_id, "tags": ["Release", "RC1"]},
                auth_context=ctx,
                api_key="reqlo_x",
            )
            assert replaced.success is True, replaced.error_code
            assert replaced.data == {"id": baseline_id, "tags": ["RC1", "Release"]}

            listed = group._handle_list(
                params={"workspace_id": str(workspace.id), "tag": "release"},
                auth_context=ctx,
                api_key="reqlo_x",
            )
            assert listed.success is True
            assert listed.data["count"] == 1
            assert listed.data["baselines"][0]["tags"] == ["RC1", "Release"]

            detail = group._handle_get(
                params={"id": baseline_id}, auth_context=ctx, api_key="reqlo_x"
            )
            assert detail.success is True
            assert detail.data["baseline"]["tags"] == ["RC1", "Release"]
        finally:
            TenantContext.clear_tenant()

    def test_invalid_label_is_validation_error(self) -> None:
        tenant, _, workspace, ctx = _make_tenant_workspace_ctx("tag-mcp-invalid")
        group = BaselineToolGroup()

        TenantContext.set_tenant(tenant.id)
        try:
            created = group._handle_create(
                params={
                    "workspace_id": str(workspace.id),
                    "scope": "project",
                    "name": "invalid-tag-baseline",
                },
                auth_context=ctx,
                api_key="reqlo_x",
            )
            result = group._handle_set_tags(
                params={"id": created.data["baseline_id"], "tags": ["bad\nlabel"]},
                auth_context=ctx,
                api_key="reqlo_x",
            )
        finally:
            TenantContext.clear_tenant()

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"


class TestBaselineSetTagsFencedKey:
    def test_fenced_key_rejects_foreign_workspace_baseline(self) -> None:
        tenant = Tenant.objects.create(
            name=f"tag-fence-{uuid.uuid4().hex[:8]}",
            slug=f"tag-fence-{uuid.uuid4().hex[:8]}",
        )
        user = User.objects.create(
            username=f"tag-fence-{uuid.uuid4().hex[:8]}",
            email=f"tag-fence-{uuid.uuid4().hex[:8]}@t.test",
            tenant=tenant,
        )
        set_request_tenant(tenant.id)
        try:
            fenced_workspace = Workspace.objects.create(
                tenant=tenant, name="fence-a", preset={"name": "standard"}
            )
            target_workspace = Workspace.objects.create(
                tenant=tenant, name="fence-b", preset={"name": "standard"}
            )
            UserRole.objects.create(
                tenant=tenant,
                user=user,
                workspace=target_workspace,
                role=ROLE_ADMIN,
            )
            baseline = BaselineSnapshot.unscoped.create(
                tenant=tenant,
                workspace_id=target_workspace.id,
                scope="project",
                name="fenced-baseline",
            )
        finally:
            clear_request_tenant()

        key = AuthenticationService().create_api_key(
            user_id=user.id,
            tenant_id=tenant.id,
            name="f4-2-mcp-fenced",
            principal_type="agent",
            scope="write",
            workspace_ids=[str(fenced_workspace.id)],
            expires_at=timezone.now() + timedelta(days=1),
        )

        result = ToolRegistry().dispatch_request(
            tool_name="baseline.set_tags",
            params={"id": str(baseline.id), "tags": ["RC1"]},
            api_key=key.plaintext,
        )

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        assert ERROR_CODE_MAP[result.error_code] == -32001
