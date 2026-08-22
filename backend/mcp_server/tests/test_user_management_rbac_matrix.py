# backend/mcp_server/tests/test_user_management_rbac_matrix.py
"""User-management RBAC matrix through the real ToolRegistry, driven from
the SAME matrix constant the REST-side test consumes (rest_api/tests/
test_user_management_rbac_matrix.py) — see auth_tenancy/tests/
user_management_matrix.py. Mirrors test_mcp_rbac_role_matrix.py's
real-DB-role-resolution style (no mocked authz service, real API key,
real ToolRegistry.dispatch_request)."""
from __future__ import annotations

import uuid

import pytest

from auth_tenancy.models import ROLE_ADMIN, ROLE_APPROVER, ROLE_EDITOR, ROLE_VIEWER, TenantRole, UserRole
from auth_tenancy.services.authentication import AuthenticationService
from auth_tenancy.tests.user_management_matrix import ACTIONS, USER_MANAGEMENT_MATRIX
from mcp_server.tool_registry import ToolRegistry
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace


_ACTION_TO_TOOL_CALL = {
    "user.create": ("user.create", lambda ids: {"username": f"u-{uuid.uuid4().hex[:8]}", "email": f"{uuid.uuid4().hex[:8]}@t.test", "password": "a-real-password-123"}),
    "user.activate": ("user.activate", lambda ids: {"user_id": str(ids["target"])}),
    "user.deactivate": ("user.deactivate", lambda ids: {"user_id": str(ids["target"])}),
    "workspace.assign_role": ("user.assign_role", lambda ids: {"user_id": str(ids["target"]), "workspace_id": str(ids["workspace"]), "role": "viewer", "preset": "extended"}),
    "workspace.suspend_role": ("user.suspend_role", lambda ids: {"user_id": str(ids["target"]), "workspace_id": str(ids["workspace"]), "role": "editor"}),
    "workspace.reactivate_role": ("user.reactivate_role", lambda ids: {"user_id": str(ids["target"]), "workspace_id": str(ids["workspace"]), "role": "editor"}),
    "tenant.assign_admin": ("user.assign_tenant_admin", lambda ids: {"user_id": str(ids["target"])}),
    "tenant.revoke_admin": ("user.revoke_tenant_admin", lambda ids: {"user_id": str(ids["target"])}),
}


def _setup_caller_and_target(role_label: str):
    """Create a tenant/workspace/caller (with role_label's role) + a
    separate target user + an API key for the caller. The target
    additionally gets an editor role in the workspace so there's
    something to suspend/reactivate (and something to deactivate that
    isn't the caller itself). The target is always a DIFFERENT user
    from the caller, and (for the "no-role" case) the assign_role
    matrix scenario uses role="viewer" (never "admin"), so the SEC-05
    first-admin-bootstrap exception (self-targeted admin-role
    assignment in an admin-less workspace) never accidentally fires
    here regardless of workspace admin state.
    """
    slug = f"umm-{role_label}-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name=slug, slug=slug, is_active=True)
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="WS", preset={"name": "extended"})
        caller = User.objects.create(username=f"caller-{slug}", email=f"caller-{slug}@t.test", tenant=tenant)
        target = User.objects.create(username=f"target-{slug}", email=f"target-{slug}@t.test", tenant=tenant)

        if role_label == "tenant-admin":
            TenantRole.objects.create(tenant=tenant, user=caller, role=TenantRole.ROLE_ADMIN)
        elif role_label == "workspace-admin":
            UserRole.objects.create(tenant=tenant, user=caller, workspace=workspace, role=ROLE_ADMIN)
        elif role_label in ("editor", "viewer", "approver"):
            role_map = {"editor": ROLE_EDITOR, "viewer": ROLE_VIEWER, "approver": ROLE_APPROVER}
            UserRole.objects.create(tenant=tenant, user=caller, workspace=workspace, role=role_map[role_label])
        # "no-role": no assignment at all

        UserRole.objects.create(tenant=tenant, user=target, workspace=workspace, role=ROLE_EDITOR)

        authn = AuthenticationService()
        api_key = authn.create_api_key(user_id=caller.id, tenant_id=tenant.id, name="matrix-key").plaintext
    finally:
        clear_request_tenant()

    return {"tenant": tenant, "workspace": workspace, "caller": caller, "target": target, "api_key": api_key}


@pytest.mark.django_db
@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("role_label", ["tenant-admin", "workspace-admin", "editor", "viewer", "approver", "no-role"])
def test_mcp_permission_matches_matrix(action, role_label):
    expected_allowed = USER_MANAGEMENT_MATRIX[action][role_label]
    ids = _setup_caller_and_target(role_label)
    tool_name, build_params = _ACTION_TO_TOOL_CALL[action]

    registry = ToolRegistry()  # real AuthenticationService + AuthorizationService
    params = build_params({"target": ids["target"].id, "workspace": ids["workspace"].id})
    result = registry.dispatch_request(
        tool_name=tool_name, params=params, api_key=ids["api_key"],
    )

    if expected_allowed:
        assert result.error_code != "PERMISSION_DENIED", (
            f"{role_label} should be ALLOWED to call {tool_name} but got "
            f"{result.error_code!r}: {result.message!r}"
        )
    else:
        assert result.success is False and result.error_code == "PERMISSION_DENIED", (
            f"{role_label} should be DENIED for {tool_name} but got "
            f"success={result.success!r} error_code={result.error_code!r}: {result.message!r}"
        )
