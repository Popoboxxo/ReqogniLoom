"""E1.3 — MCP ``workspace.list`` is fence-filtered (Plan E, issue #1444).

A workspace-scoped API key must be able to list *its* workspaces: the
dispatcher skips the fail-closed fence denial for ``FENCE_FILTERED_TOOLS`` when
the call names no workspace, and ``WorkspaceService.list_workspaces`` narrows
the result to the fence. Every other workspace-less tool keeps the ``-32001``
scope denial (``workspace.query {}`` is the pinned counter-example).
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from auth_tenancy.models import ROLE_EDITOR, UserRole
from auth_tenancy.services.authentication import AuthenticationService
from mcp_server.tool_registry import ToolRegistry
from mcp_server.workspace_scope import FENCE_FILTERED_TOOLS
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

pytestmark = pytest.mark.django_db


@pytest.fixture
def env() -> tuple[Tenant, User, Workspace, Workspace, str]:
    slug = f"e13-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name=f"T-{slug}", slug=slug, is_active=True)
    user = User.objects.create(
        username=f"user-{slug}", email=f"{slug}@t.test", tenant=tenant
    )
    set_request_tenant(tenant.id)
    try:
        ws_a = Workspace.objects.create(tenant=tenant, name=f"WS-A-{slug}", preset={})
        ws_b = Workspace.objects.create(tenant=tenant, name=f"WS-B-{slug}", preset={})
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=ws_a, role=ROLE_EDITOR
        )
    finally:
        clear_request_tenant()

    result = AuthenticationService().create_api_key(
        user_id=user.id,
        tenant_id=tenant.id,
        name="e13-fenced",
        principal_type="agent",
        scope="author",
        workspace_ids=[str(ws_a.id)],
        expires_at=timezone.now() + timedelta(days=1),
    )
    return tenant, user, ws_a, ws_b, result.plaintext


def test_workspace_list_is_registered_as_fence_filtered() -> None:
    assert "workspace.list" in FENCE_FILTERED_TOOLS


def test_fenced_key_lists_only_its_workspaces(env) -> None:
    _tenant, _user, ws_a, ws_b, api_key = env

    result = ToolRegistry().dispatch_request(
        tool_name="workspace.list", params={}, api_key=api_key
    )

    assert result.success, (result.error_code, result.message)
    assert result.data["count"] == 1, result.data
    ids = [row["id"] for row in result.data["workspaces"]]
    assert ids == [str(ws_a.id)]
    assert str(ws_b.id) not in ids


def test_workspace_get_context_without_workspace_keeps_scope_denial(env) -> None:
    """Global (workspace-less) tool calls keep the ``-32001`` fence denial.

    The Plan E text names ``workspace.query {}`` here; no such MCP tool exists
    in this tree (see the workspace.* names in
    ``mcp_server/tools/cross_cutting.py`` and ``mcp_server/tools/admin.py``), so
    the same global-call shape is pinned with ``workspace.get_context {}``.
    """
    _tenant, _user, _ws_a, _ws_b, api_key = env

    result = ToolRegistry().dispatch_request(
        tool_name="workspace.get_context", params={}, api_key=api_key
    )

    assert not result.success
    assert result.error_code == "PERMISSION_DENIED", result.message
