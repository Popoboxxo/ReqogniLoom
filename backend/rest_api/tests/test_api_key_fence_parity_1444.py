"""#1444 — one agent key, one decision: REST and MCP fence-filtered lists.

The issue reports the same workspace-scoped agent key behaving oppositely at the
two doors: ``GET /api/v1/workspaces/`` answered a *role-matrix* denial while MCP
``workspace.list`` / ``requirement.query`` answered 200 / a workspace-fence
error.  E1.1–E1.4 aligned the workspace-scoped paths; the remaining drift is the
**fence-filtered list**:

* REST exempts such a list from the *fence precheck only* and still evaluates the
  RBAC matrix against :func:`fenced_collection_roles` — an owner with no role in
  any fence workspace gets 403 ``API_KEY_NO_OWNER_ROLE_IN_FENCE_DENIAL``.
* MCP treated ``FENCE_FILTERED_TOOLS`` as exempt from **both** the fence and the
  read gate, so the same key got ``200`` with an empty list. Its workspace-less
  role resolution also used the tenant-wide union, which includes roles held
  *outside* the fence.

Both doors now decide with the same shared helper from ``auth_tenancy``
(:func:`auth_tenancy.resource_scope.fence_filtered_list_denial`), so the verdict
and the denial text are identical.

The documented, design-bound difference stays: MCP accepts API keys only
(REQ-L2-MC-006 / REQ-052), so a JWT request has no MCP counterpart. That is a
credential-type difference, not an authorization one, and is pinned by
``test_api_key_principal_matrix_1444.py``.
"""
from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any

import pytest
from django.test import Client as DjangoClient
from django.utils import timezone
from rest_framework.test import APIClient

from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import ROLE_EDITOR, UserRole
from auth_tenancy.resource_scope import (
    API_KEY_NO_OWNER_ROLE_IN_FENCE_DENIAL,
    fenced_collection_roles,
    workspace_fence_denial,
)
from auth_tenancy.services.authentication import AuthenticationService
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, Tenant, User, Workspace
from presets.models import WorkspacePresetConfig

pytestmark = pytest.mark.django_db

SCOPE_MESSAGE_FRAGMENT = "restricted to specific workspaces"


@pytest.fixture(autouse=True)
def _reset_mcp_view_singletons(monkeypatch: pytest.MonkeyPatch) -> None:
    """The /mcp/ view keeps its registry/handler singletons module-global."""
    monkeypatch.setattr("mcp_server.views._tool_registry", None)
    monkeypatch.setattr("mcp_server.views._protocol_handler", None)


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _seed() -> dict[str, Any]:
    slug = f"p1444-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name=f"T-{slug}", slug=slug, is_active=True)
    user = User.objects.create(
        username=f"user-{slug}", email=f"{slug}@t.test", tenant=tenant
    )
    user.set_password("hunter2pass")
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        ws_a = Workspace.objects.create(
            tenant=tenant, name=f"WS-A-{slug}", preset={"name": "extended"}
        )
        ws_b = Workspace.objects.create(
            tenant=tenant, name=f"WS-B-{slug}", preset={"name": "extended"}
        )
        req_a = _requirement(tenant, ws_a, "parity-req-a")
    finally:
        clear_request_tenant()

    for workspace in (ws_a, ws_b):
        WorkspacePresetConfig.unscoped.create(
            tenant=tenant,
            workspace=workspace,
            active_tier="extended",
            terminology_profile="dev_mode",
            downgrade_policy="allow",
        )
    return {
        "tenant": tenant,
        "user": user,
        "ws_a": ws_a,
        "ws_b": ws_b,
        "req_a": req_a,
    }


def _requirement(tenant: Tenant, workspace: Workspace, title: str) -> Requirement:
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    return Requirement.objects.create(
        tenant=tenant,
        workspace=workspace,
        artifact=artifact,
        title=title,
        description="1444 parity fixture",
    )


def _grant(tenant: Tenant, user: User, workspace: Workspace, role: str) -> None:
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=role
        )
    finally:
        clear_request_tenant()


def _mint_agent_key(
    tenant: Tenant, user: User, *, scope: str, fence: list[Workspace]
) -> str:
    return (
        AuthenticationService()
        .create_api_key(
            user_id=user.id,
            tenant_id=tenant.id,
            name=f"p1444-{scope}-{uuid.uuid4().hex[:6]}",
            principal_type="agent",
            scope=scope,
            workspace_ids=[str(ws.id) for ws in fence],
            expires_at=timezone.now() + timedelta(days=1),
        )
        .plaintext
    )


# ---------------------------------------------------------------------------
# Door helpers — both return (allowed, code, message)
# ---------------------------------------------------------------------------


def _rest(creds: dict[str, str], path: str) -> tuple[bool, str | None, str | None]:
    client = APIClient()
    client.credentials(**creds)
    response = client.get(path)
    if response.status_code < 400:
        return True, None, None
    error = response.json().get("error", {})
    return False, error.get("code"), error.get("message")


def _mcp(
    creds: dict[str, str], tool: str, arguments: dict[str, Any]
) -> tuple[bool, str | None, str | None]:
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }
    response = DjangoClient().post(
        "/mcp/", data=json.dumps(body), content_type="application/json", **creds
    )
    payload = response.json()
    if "error" in payload:
        error = payload["error"]
        return False, str(error.get("code")), error.get("message")
    result = payload.get("result") or {}
    if result.get("isError"):
        return (
            False,
            str(result.get("error_code") or result.get("errorCode") or "isError"),
            str(result.get("content") or result.get("message") or ""),
        )
    return True, None, None


# ---------------------------------------------------------------------------
# The repro: owner holds no role inside the fence
# ---------------------------------------------------------------------------


def test_fence_filtered_list_denies_the_same_key_at_both_doors() -> None:
    """REST and MCP must answer the identical 403 / -32001 for the same key.

    Owner is an Editor in B; the agent key is fenced to A. The key therefore
    cannot see any workspace, and neither door may pretend the list succeeded.
    """
    env = _seed()
    tenant, user, ws_a, ws_b = (
        env["tenant"],
        env["user"],
        env["ws_a"],
        env["ws_b"],
    )
    _grant(tenant, user, ws_b, ROLE_EDITOR)
    key = _mint_agent_key(tenant, user, scope="write", fence=[ws_a])
    creds = {"HTTP_X_API_KEY": key}

    rest_allowed, rest_code, rest_message = _rest(creds, "/api/v1/workspaces/")
    mcp_allowed, mcp_code, mcp_message = _mcp(creds, "workspace.list", {})

    assert rest_allowed is False
    assert rest_code == "PERMISSION_DENIED"
    assert rest_message == API_KEY_NO_OWNER_ROLE_IN_FENCE_DENIAL

    assert mcp_allowed is False, "MCP must not answer 200 where REST answers 403"
    assert mcp_code == "-32001"
    assert mcp_message == API_KEY_NO_OWNER_ROLE_IN_FENCE_DENIAL


def test_fence_filtered_list_allows_both_doors_when_the_owner_has_a_role() -> None:
    """Positive control: the alignment must not over-deny the working case."""
    env = _seed()
    tenant, user, ws_a = env["tenant"], env["user"], env["ws_a"]
    _grant(tenant, user, ws_a, ROLE_EDITOR)
    key = _mint_agent_key(tenant, user, scope="write", fence=[ws_a])
    creds = {"HTTP_X_API_KEY": key}

    assert _rest(creds, "/api/v1/workspaces/")[0] is True
    assert _mcp(creds, "workspace.list", {})[0] is True


# ---------------------------------------------------------------------------
# The foreign-workspace fence: identical denial text at both doors
# ---------------------------------------------------------------------------


def test_foreign_workspace_fence_text_is_identical_at_both_doors() -> None:
    env = _seed()
    tenant, user, ws_a, ws_b = (
        env["tenant"],
        env["user"],
        env["ws_a"],
        env["ws_b"],
    )
    _grant(tenant, user, ws_a, ROLE_EDITOR)
    key = _mint_agent_key(tenant, user, scope="write", fence=[ws_a])
    creds = {"HTTP_X_API_KEY": key}

    expected = workspace_fence_denial([str(ws_a.id)], ws_b.id)
    assert expected is not None
    assert SCOPE_MESSAGE_FRAGMENT in expected

    rest_allowed, rest_code, rest_message = _rest(
        creds, f"/api/v1/requirements/?workspace_id={ws_b.id}"
    )
    mcp_allowed, mcp_code, mcp_message = _mcp(
        creds, "requirement.query", {"workspace_id": str(ws_b.id)}
    )

    assert rest_allowed is False
    assert rest_code == "PERMISSION_DENIED"
    assert rest_message == expected

    assert mcp_allowed is False
    assert mcp_code == "-32001"
    assert mcp_message == expected


# ---------------------------------------------------------------------------
# Root cause: MCP's workspace-less role resolution must be fence-scoped
# ---------------------------------------------------------------------------


def test_mcp_workspaceless_roles_are_fence_scoped() -> None:
    """A role held only *outside* the fence must not count on the MCP path.

    REST narrows a fenced key's roles to the fence
    (``TenantContextService.build_auth_context`` + ``fenced_collection_roles``);
    MCP used the tenant-wide union instead, so the two doors decided with
    different role tuples even where their verdicts happened to agree.
    """
    env = _seed()
    tenant, user, ws_a, ws_b = (
        env["tenant"],
        env["user"],
        env["ws_a"],
        env["ws_b"],
    )
    _grant(tenant, user, ws_b, ROLE_EDITOR)
    key = _mint_agent_key(tenant, user, scope="write", fence=[ws_a])

    from mcp_server.tool_registry import ToolRegistry

    registry = ToolRegistry()
    set_request_tenant(tenant.id)
    try:
        ctx, err = registry._validate_api_key(key)
        assert err is None
        assert isinstance(ctx, AuthContext)
        resolved = registry._resolve_roles(ctx, None)

        assert resolved.active_roles == fenced_collection_roles(resolved) == ()
        assert "editor" not in resolved.active_roles
    finally:
        clear_request_tenant()


def test_shared_roles_helper_is_the_single_source() -> None:
    """The shared helper is what both transports must resolve against."""
    env = _seed()
    tenant, user, ws_a = env["tenant"], env["user"], env["ws_a"]
    _grant(tenant, user, ws_a, ROLE_EDITOR)
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=(),
        auth_method=AuthMethod.API_KEY,
        api_key_workspace_ids=(str(ws_a.id),),
    )
    set_request_tenant(tenant.id)
    try:
        assert fenced_collection_roles(ctx) == (ROLE_EDITOR,)
    finally:
        clear_request_tenant()
