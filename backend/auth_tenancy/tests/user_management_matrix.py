"""Single source of truth for user-management permission decisions.

Imported by BOTH the MCP test suite (mcp_server/tests/
test_user_management_rbac_matrix.py) and the REST test suite
(rest_api/tests/test_user_management_rbac_matrix.py) so the two
transports are proven to enforce identical decisions from one shared
definition — never hand-duplicated (multi-user management design spec,
section 3).

Roles here are the CALLER's roles, not a target's roles:
  "tenant-admin"    — caller holds TenantRole(admin) in the tenant
  "workspace-admin" — caller holds UserRole(admin) in the target workspace
  "editor"          — caller holds UserRole(editor) in the target workspace
  "viewer"          — caller holds UserRole(viewer) in the target workspace
  "approver"        — caller holds UserRole(approver) in the target workspace
  "no-role"         — caller has no role at all in the tenant/workspace
"""
from __future__ import annotations

ROLES = ("tenant-admin", "workspace-admin", "editor", "viewer", "approver", "no-role")

# action -> {role -> expected allowed}
USER_MANAGEMENT_MATRIX: dict[str, dict[str, bool]] = {
    "user.create": {
        "tenant-admin": True,
        "workspace-admin": False,
        "editor": False,
        "viewer": False,
        "approver": False,
        "no-role": False,
    },
    "user.activate": {
        "tenant-admin": True,
        "workspace-admin": False,
        "editor": False,
        "viewer": False,
        "approver": False,
        "no-role": False,
    },
    "user.deactivate": {
        "tenant-admin": True,
        "workspace-admin": False,
        "editor": False,
        "viewer": False,
        "approver": False,
        "no-role": False,
    },
    "workspace.assign_role": {
        "tenant-admin": True,
        "workspace-admin": True,
        "editor": False,
        "viewer": False,
        "approver": False,
        "no-role": False,
    },
    "workspace.suspend_role": {
        "tenant-admin": True,
        "workspace-admin": True,
        "editor": False,
        "viewer": False,
        "approver": False,
        "no-role": False,
    },
    "workspace.reactivate_role": {
        "tenant-admin": True,
        "workspace-admin": True,
        "editor": False,
        "viewer": False,
        "approver": False,
        "no-role": False,
    },
    "tenant.assign_admin": {
        "tenant-admin": True,
        "workspace-admin": False,
        "editor": False,
        "viewer": False,
        "approver": False,
        "no-role": False,
    },
    "tenant.revoke_admin": {
        "tenant-admin": True,
        "workspace-admin": False,
        "editor": False,
        "viewer": False,
        "approver": False,
        "no-role": False,
    },
    "user.list": {
        # Fix round 3 (I-1): tightened to tenant-admin-only on both
        # transports (previously MCP also accepted a plain workspace-admin,
        # strictly more permissive than REST's GET /api/v1/users/).
        "tenant-admin": True,
        "workspace-admin": False,
        "editor": False,
        "viewer": False,
        "approver": False,
        "no-role": False,
    },
}

ACTIONS = tuple(USER_MANAGEMENT_MATRIX.keys())
