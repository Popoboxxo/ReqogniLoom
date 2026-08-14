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

The second half of this module (issue #359) drops the sink and drives the REAL
tool groups and domain services, to prove that destructive admin/user/permission
tools are blocked by the SERVER for non-admin callers rather than by client-side
blocklist discipline.

leaf_id : COMP-MC-002 (ToolRegistry) + COMP-AT-001/002 (role resolution)
req_id  : REQ-127, REQ-L2-MC-007 / GitHub #359
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import (
    ROLE_ADMIN,
    ROLE_APPROVER,
    ROLE_EDITOR,
    ROLE_VIEWER,
    ItemPermission,
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


@dataclass(frozen=True)
class _Identity:
    """A real tenant/user/workspace/API-key quadruple for one role."""

    api_key: str
    tenant: Tenant
    user: User
    workspace: Workspace


def _setup_identity(role: str) -> _Identity:
    """Create a tenant + user holding ``role`` in a workspace + an API key."""
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
    return _Identity(
        api_key=key.plaintext, tenant=tenant, user=user, workspace=workspace
    )


def _setup_api_key_identity(role: str) -> tuple[str, Workspace]:
    """Create a user with ``role`` + an API key. Return (plaintext_key, workspace)."""
    identity = _setup_identity(role)
    return identity.api_key, identity.workspace


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


# ---------------------------------------------------------------------------
# Issue #359 — server-side enforcement of destructive admin/user tools
# ---------------------------------------------------------------------------
#
# An external integrator black-box-tested the MCP server and reported that the
# blocklist for admin/user/permission tools looked like a purely client-side
# convention: ``tools/list`` hands an admin-scoped token every tool with no
# marking, so nothing in the protocol says which ones are meant to be
# off-limits. The question this suite answers is the one that actually
# matters: does a NON-admin token get stopped *by the server* when it calls
# them?
#
# The per-group suites (test_backup_tool_group.py, test_admin_tool_group.py,
# test_permissions_tool_group.py) mock the underlying domain service and make
# it raise ``PermissionDeniedError``, so they only prove the MCP wrapper's
# error *mapping* — not that anything enforces the rule. The suites below
# drive the whole stack: real API key -> real role resolution from ``UserRole``
# -> real ToolRegistry gate -> real tool group -> real domain service.
#
# Every call below is constructed to be non-destructive even if the gate is
# broken: ids point at rows that do not exist, and ``workspace.delete`` carries
# a deliberately wrong captcha (``WorkspaceService.delete_workspace`` checks
# the admin role BEFORE the captcha, so a regression surfaces as
# VALIDATION_ERROR instead of a deleted workspace).

# Tools in the admin-facing namespaces that are admin-only BY DESIGN and must
# stay unreachable for every non-admin role.
_ADMIN_ONLY_NAMESPACES = ("admin.", "audit.", "events.", "permissions.", "user.")

# Documented, deliberate exceptions — reachable without the admin role:
#   audit.ai_review    — mirrors the Phase-3 REST endpoint, any authenticated
#                        caller with workspace access may run it (see the
#                        "No admin gate" note in AuditToolGroup._handle_ai_review).
#   permissions.check  — self-introspection only: the handler hard-codes
#                        ``user_id=auth_context.user_id``, so a caller can only
#                        ask about their own effective permission.
_ADMIN_NAMESPACE_NON_ADMIN_BY_DESIGN = frozenset(
    {
        "audit.ai_review",
        "permissions.check",
    }
)

# ``permissions.revoke`` needs a real ItemPermission row to reach its gate
# (the handler resolves the row before delegating), so it has its own test
# below rather than a stub-params entry here.
_COVERED_ELSEWHERE = frozenset({"permissions.revoke"})


def _admin_only_calls(identity: _Identity) -> Dict[str, Dict[str, Any]]:
    """Return ``tool_name -> params`` for every admin-only tool under test.

    Parameters are valid enough to get past parameter validation and reach the
    authorisation gate, but point at non-existent rows so a broken gate fails
    loudly (NOT_FOUND / VALIDATION_ERROR) instead of destroying data.
    """
    workspace_id = str(identity.workspace.id)
    stranger_id = str(uuid.uuid4())
    return {
        # BackupToolGroup (admin_ops services enforce admin).
        "admin.backup_create": {},
        "admin.backup_list": {},
        "admin.restore": {
            "backup_id": str(uuid.uuid4()),
            "confirmation_text": "RESTORE",
        },
        # AuditToolGroup (_check_admin inside the group).
        "audit.query": {},
        "events.dlq_list": {"workspace_id": workspace_id},
        "events.dlq_replay": {
            "event_id": str(uuid.uuid4()),
            "workspace_id": workspace_id,
        },
        # PermissionsToolGroup (ItemPermissionService enforces admin).
        "permissions.list": {"workspace_id": workspace_id, "user_id": stranger_id},
        "permissions.set_rule": {
            "workspace_id": workspace_id,
            "user_id": stranger_id,
            "permission_level": "write",
        },
        # UsersToolGroup (_check_admin inside the group).
        "user.create": {
            "username": f"intruder-{uuid.uuid4().hex[:8]}",
            "email": f"intruder-{uuid.uuid4().hex[:8]}@t.test",
            "password": "not-a-real-password",
        },
        "user.deactivate": {"user_id": stranger_id},
        "user.list": {},
        # Not a bootstrap candidate (foreign target, non-admin role), so the
        # SEC-05 self-bootstrap exemption does not apply.
        "user.assign_role": {
            "user_id": stranger_id,
            "workspace_id": workspace_id,
            "role": ROLE_VIEWER,
            "preset": "extended",
        },
        # AdminToolGroup (WorkspaceService enforces admin).
        "workspace.close": {"workspace_id": workspace_id},
        "workspace.reactivate": {"workspace_id": workspace_id},
        "workspace.delete": {
            "workspace_id": workspace_id,
            # Wrong on purpose — the admin gate runs first.
            "confirmation_text": "NOT-THE-WORKSPACE-NAME",
        },
    }


def _admin_only_tool_names() -> list[str]:
    """Tool names covered by :func:`_admin_only_calls` (no DB access needed)."""
    dummy = _Identity(
        api_key="reqlo_dummy",
        tenant=Tenant(id=uuid.uuid4()),
        user=User(id=uuid.uuid4()),
        workspace=Workspace(id=uuid.uuid4()),
    )
    return sorted(_admin_only_calls(dummy))


@pytest.mark.django_db
@pytest.mark.parametrize("role", [ROLE_EDITOR, ROLE_APPROVER, ROLE_VIEWER])
@pytest.mark.parametrize("tool_name", _admin_only_tool_names())
def test_admin_only_tools_are_denied_server_side_for_non_admin_roles(
    role: str, tool_name: str
) -> None:
    """Issue #359: the server — not the client — blocks destructive admin tools.

    The ``editor``/``approver`` rows are the load-bearing ones: both pass the
    generic WRITE gate in :meth:`ToolRegistry.dispatch_request`, so a
    PERMISSION_DENIED here can only come from the tool group's or the domain
    service's admin check. ``viewer`` additionally covers the read-classified
    admin tools (``admin.backup_list``, ``audit.query``, ``user.list``,
    ``permissions.list``), which bypass the WRITE gate entirely.
    """
    identity = _setup_identity(role)
    registry = ToolRegistry()  # real groups, real auth/authz services
    params = _admin_only_calls(identity)[tool_name]

    result = registry.dispatch_request(
        tool_name=tool_name, params=params, api_key=identity.api_key
    )

    assert result.success is False, (
        f"[{role}] '{tool_name}' succeeded server-side — the admin gate is "
        f"missing, blocking it is left to client-side discipline (issue #359)."
    )
    assert result.error_code == "PERMISSION_DENIED", (
        f"[{role}] '{tool_name}' must be PERMISSION_DENIED, got "
        f"{result.error_code!r}: {result.message!r}"
    )


@pytest.mark.django_db
@pytest.mark.parametrize("role", [ROLE_EDITOR, ROLE_VIEWER])
def test_permissions_revoke_is_denied_and_leaves_the_rule_intact(role: str) -> None:
    """``permissions.revoke`` on an EXISTING rule must be denied for non-admins.

    Split out from the matrix above because the handler resolves the
    ``ItemPermission`` row before delegating to the service, so a non-existent
    id would short-circuit with NOT_FOUND and never exercise the gate.
    """
    identity = _setup_identity(role)
    set_request_tenant(identity.tenant.id)
    try:
        rule = ItemPermission.objects.create(
            tenant=identity.tenant,
            user=identity.user,
            workspace=identity.workspace,
            permission_level="read",
        )
    finally:
        clear_request_tenant()

    registry = ToolRegistry()
    result = registry.dispatch_request(
        tool_name="permissions.revoke",
        params={
            "permission_id": str(rule.id),
            "workspace_id": str(identity.workspace.id),
        },
        api_key=identity.api_key,
    )

    assert result.error_code == "PERMISSION_DENIED", (
        f"[{role}] permissions.revoke must be PERMISSION_DENIED, got "
        f"{result.error_code!r}: {result.message!r}"
    )
    assert ItemPermission.unscoped.filter(id=rule.id).exists(), (
        f"[{role}] permissions.revoke deleted the rule despite being denied"
    )


def test_every_admin_namespace_tool_is_covered_by_the_rbac_matrix() -> None:
    """Anti-drift guard: a new ``admin.*``/``user.*``/… tool must be classified.

    Issue #359's underlying complaint is drift: a hand-maintained list of
    "dangerous" tool names silently goes stale when a tool group grows a new
    tool. This test fails as soon as a tool lands in an admin-facing namespace
    without either being covered by the denial matrix above or being explicitly
    declared non-admin by design.
    """
    registry = ToolRegistry()
    registry._ensure_groups()

    registered: set[str] = set()
    seen_groups: set[int] = set()
    for group in registry._groups.values():
        if id(group) in seen_groups:
            continue
        seen_groups.add(id(group))
        for schema in group.get_tool_schemas():
            registered.add(schema["name"])

    in_admin_namespace = {
        name
        for name in registered
        if name.startswith(_ADMIN_ONLY_NAMESPACES)
    }
    uncovered = (
        in_admin_namespace
        - set(_admin_only_tool_names())
        - _ADMIN_NAMESPACE_NON_ADMIN_BY_DESIGN
        - _COVERED_ELSEWHERE
    )

    assert not uncovered, (
        "Admin-namespace tools without an RBAC classification: "
        f"{sorted(uncovered)}. Add them to _admin_only_calls() (admin-only) or "
        "to _ADMIN_NAMESPACE_NON_ADMIN_BY_DESIGN with a reason."
    )
