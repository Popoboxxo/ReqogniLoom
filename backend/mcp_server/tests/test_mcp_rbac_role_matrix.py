"""
MCP RBAC role matrix through the ToolRegistry with REAL role resolution (REQ-127).

Unlike ``test_tool_registry.py`` (which mocks the authz service and therefore
never exercises DB role resolution) and ``test_mcp_api_key_roles.py`` (which
needs a live Docker stack on localhost:8000), this suite drives
``ToolRegistry.dispatch_request`` with the REAL ``AuthenticationService`` and
``AuthorizationService`` against real ``ApiKey`` / ``UserRole`` rows.

It is the security-critical proof for REQ-127: an MCP request authenticated with
an API key must have the caller's workspace roles loaded and propagated into the
dispatch context so RBAC gates write tools correctly — the core failure case
being a tool call that carries NO ``workspace_id`` argument, where the pre-fix
code left ``active_roles`` empty and blocked every write with PERMISSION_DENIED.

Matrix per role (admin / editor / viewer / approver):
    read  tool : ``requirement.get``     -> never RBAC-denied
    write tool : ``requirement.create``  -> viewer DENIED, others pass the gate
    both variants: with and without ``workspace_id`` in the tool arguments.

A mock tool group is registered as the execution sink so the assertions isolate
role resolution + the RBAC gate from the real tool implementations.

leaf_id : COMP-MC-002 (ToolRegistry) + COMP-AT-001/002 (role resolution)
req_id  : REQ-127
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import (
    ROLE_ADMIN,
    ROLE_APPROVER,
    ROLE_EDITOR,
    ROLE_VIEWER,
    UserRole,
)
from auth_tenancy.services.authentication import AuthenticationService
from mcp_server.protocol_handler import ToolResult
from mcp_server.tool_registry import ToolRegistry
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

_READ_TOOL = "requirement.get"
_WRITE_TOOL = "requirement.create"

# Every role may read; only these may write.
_WRITE_ALLOWED = {
    ROLE_ADMIN: True,
    ROLE_EDITOR: True,
    ROLE_APPROVER: True,
    ROLE_VIEWER: False,
}


def _setup_api_key_identity(role: str) -> tuple[str, Workspace]:
    """Create a user with ``role`` + an API key. Return (plaintext_key, workspace)."""
    slug = f"mcp-{role}-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name=f"T-{role}", slug=slug, is_active=True)
    user = User.objects.create(
        username=f"user-{slug}", email=f"{slug}@t.test", tenant=tenant
    )
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=f"WS-{role}", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=role
        )
    finally:
        clear_request_tenant()

    key = AuthenticationService().create_api_key(
        user_id=user.id, tenant_id=tenant.id, name="mcp-matrix-key"
    )
    return key.plaintext, workspace


def _registry_with_sink() -> tuple[ToolRegistry, MagicMock]:
    """Real auth/authz ToolRegistry with a mock 'requirement' execution sink."""
    registry = ToolRegistry()  # real AuthenticationService + AuthorizationService
    sink = MagicMock()
    sink.execute_tool.return_value = ToolResult.ok({"requirement": {"id": "x"}})
    registry.register_groups({"requirement": sink})
    return registry, sink


@pytest.mark.django_db
@pytest.mark.parametrize("role", list(_WRITE_ALLOWED))
@pytest.mark.parametrize("with_workspace_id", [True, False], ids=["ws_arg", "no_ws_arg"])
def test_mcp_write_tool_rbac_uses_real_role_resolution(
    role: str, with_workspace_id: bool
) -> None:
    """Write tool via API key: viewer denied, others pass the RBAC gate.

    The ``no_ws_arg`` variant is the exact REQ-127 finding: without a
    ``workspace_id`` argument the API-key caller's roles must still be resolved
    (global fallback), otherwise every write would be wrongly denied.
    """
    api_key, workspace = _setup_api_key_identity(role)
    registry, sink = _registry_with_sink()

    params: dict = {"title": "matrix"}
    if with_workspace_id:
        params["workspace_id"] = str(workspace.id)

    result = registry.dispatch_request(
        tool_name=_WRITE_TOOL, params=params, api_key=api_key
    )

    if _WRITE_ALLOWED[role]:
        # Role resolved from the DB -> RBAC gate passes -> execution reached.
        assert result.error_code != "PERMISSION_DENIED", (
            f"[{role}/ws={with_workspace_id}] write wrongly denied — API-key "
            f"role resolution failed (REQ-127 regression): {result.message!r}"
        )
        assert sink.execute_tool.called, "execution sink must be reached"
    else:
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED", (
            f"[viewer/ws={with_workspace_id}] write must be PERMISSION_DENIED, "
            f"got {result.error_code!r}"
        )
        sink.execute_tool.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("role", list(_WRITE_ALLOWED))
@pytest.mark.parametrize("with_workspace_id", [True, False], ids=["ws_arg", "no_ws_arg"])
def test_mcp_read_tool_never_rbac_denied(
    role: str, with_workspace_id: bool
) -> None:
    """Read tool via API key must never be RBAC-denied for any role."""
    api_key, workspace = _setup_api_key_identity(role)
    registry, sink = _registry_with_sink()

    params: dict = {"id": str(uuid.uuid4())}
    if with_workspace_id:
        params["workspace_id"] = str(workspace.id)

    result = registry.dispatch_request(
        tool_name=_READ_TOOL, params=params, api_key=api_key
    )

    assert result.error_code != "PERMISSION_DENIED", (
        f"[{role}] read must not be RBAC-denied: {result.message!r}"
    )
    assert sink.execute_tool.called


@pytest.mark.django_db
@pytest.mark.parametrize("role", list(_WRITE_ALLOWED))
def test_mcp_api_key_roles_are_propagated(role: str) -> None:
    """REQ-127: API-key context resolves the caller's roles from UserRole.

    Directly exercises the resolution helpers for both the workspace-scoped and
    the global (no workspace_id) paths — the roles must be non-empty and contain
    the assigned role in both cases.
    """
    _api_key, workspace = _setup_api_key_identity(role)
    # Rebuild the partial context the registry builds after API-key validation.
    user_role = UserRole.unscoped.get(workspace_id=workspace.id, role=role)
    ctx = AuthContext(
        user_id=user_role.user_id,
        tenant_id=user_role.tenant_id,
        active_roles=(),  # empty like a freshly validated API-key context
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid.uuid4(),
    )
    registry = ToolRegistry()

    set_request_tenant(user_role.tenant_id)
    try:
        # Global path (no workspace_id) — the REQ-127 core scenario.
        global_ctx = registry._resolve_roles(ctx, None)
        assert role in global_ctx.active_roles, (
            f"[{role}] global role resolution empty/wrong: "
            f"{global_ctx.active_roles!r}"
        )
        # Workspace-scoped path.
        scoped_ctx = registry._resolve_roles(ctx, str(workspace.id))
        assert role in scoped_ctx.active_roles, (
            f"[{role}] workspace-scoped role resolution empty/wrong: "
            f"{scoped_ctx.active_roles!r}"
        )
    finally:
        clear_request_tenant()
