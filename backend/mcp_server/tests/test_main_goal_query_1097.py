"""Tests for GitHub issue #1097: ``main_goal.query``.

``MainGoalToolGroup`` had no collection tool: a MainGoal was reachable only
through ``main_goal.read`` (by id) or ``main_goal.list_versions`` (which also
needs a workspace, but advertises the version chain oldest-first rather than a
discovery list). REST's ``GET /api/v1/main-goals/?workspace_id=`` enumerates a
workspace's main goals, so the entity was addressable but not discoverable over
MCP — the same #1080 "fetch without list" shape ``goal.query`` (#216) closed
for Goals and ``traceability.query_links`` (#1098) closed for TraceLinks.

The role contract (E3) is part of the tool's published description: "Every
member of a workspace may list that workspace's MainGoals read-only." The
result is scoped to the caller's tenant *and* the given workspace.

Style mirrors ``test_goal_query_delete.py`` / ``test_goal_tools.py``: drives the
real ``MainGoalService`` through the MCP tool group against the DB, and drives
the real ``ToolRegistry`` for the RBAC/role-contract half.
"""
from __future__ import annotations

import uuid

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tool_registry import ToolRegistry, _READ_ONLY_TOOL_NAMES
from mcp_server.tools.goals import MainGoalToolGroup
from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db

VALID_API_KEY = "reqlo_testkey1234"


def _ctx(*, tenant_id, roles=("admin",)) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id,
        active_roles=roles,
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid.uuid4(),
    )


def _tenant_and_workspace(
    tenant_name: str, workspace_name: str, *, goals_enabled: bool = True
):
    # A unique slug is required: Tenant.slug is unique and defaults to "" when
    # omitted, so the second tenant in one test would collide on it.
    tenant = Tenant.objects.create(name=tenant_name, slug=uuid.uuid4().hex[:12])
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=workspace_name, goals_enabled=goals_enabled
        )
    finally:
        TenantContext.clear_tenant()
    return tenant, workspace


def _add_workspace(
    tenant: Tenant, name: str, *, goals_enabled: bool = True
) -> Workspace:
    """Create a workspace inside an *existing* tenant."""
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name=name, goals_enabled=goals_enabled
        )
    finally:
        TenantContext.clear_tenant()


def _create_main_goal(
    group: MainGoalToolGroup, workspace_id, ctx, content: str
) -> str:
    """Create one MainGoal draft via MCP and return its id."""
    created = group.execute_tool(
        tool_name="main_goal.create_manual",
        params={"workspace_id": str(workspace_id), "content": content},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert created.success is True, f"{content!r}: {created.message}"
    return created.data["main_goal"]["id"]


# ---------------------------------------------------------------------------
# Success + shape
# ---------------------------------------------------------------------------


def test_main_goal_query_lists_all_versions_newest_first():
    tenant, workspace = _tenant_and_workspace("I1097-Q1", "W1")
    ctx = _ctx(tenant_id=tenant.id)
    group = MainGoalToolGroup()

    _create_main_goal(group, workspace.id, ctx, "First main goal")
    _create_main_goal(group, workspace.id, ctx, "Second main goal")

    result = group.execute_tool(
        tool_name="main_goal.query",
        params={"workspace_id": str(workspace.id)},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    assert result.success is True, result.message
    assert result.data["count"] == 2
    assert [mg["content"] for mg in result.data["main_goals"]] == [
        "Second main goal",
        "First main goal",
    ]
    # The payload keeps the same field set as the other main_goal.* responses.
    first = result.data["main_goals"][0]
    assert {"id", "workspace_id", "sequence_number", "content", "source", "status"} <= set(
        first
    )
    assert first["workspace_id"] == str(workspace.id)
    assert first["sequence_number"] == 2


def test_main_goal_query_empty_workspace_returns_empty_list_and_zero_count():
    tenant, workspace = _tenant_and_workspace("I1097-Q2", "W2")
    ctx = _ctx(tenant_id=tenant.id)

    result = MainGoalToolGroup().execute_tool(
        tool_name="main_goal.query",
        params={"workspace_id": str(workspace.id)},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    assert result.success is True, result.message
    assert result.data == {"main_goals": [], "count": 0}


# ---------------------------------------------------------------------------
# Workspace / tenant scoping
# ---------------------------------------------------------------------------


def test_main_goal_query_is_scoped_to_the_given_workspace_and_tenant():
    tenant_a, ws_a = _tenant_and_workspace("I1097-S1", "WsA")
    # A second workspace in the *same* tenant, to prove workspace isolation.
    ws_b = _add_workspace(tenant_a, "WsB")
    tenant_c, ws_c = _tenant_and_workspace("I1097-S3", "WsC")
    ctx_a = _ctx(tenant_id=tenant_a.id)
    ctx_c = _ctx(tenant_id=tenant_c.id)
    group = MainGoalToolGroup()

    _create_main_goal(group, ws_a.id, ctx_a, "Goal in A")
    _create_main_goal(group, ws_b.id, ctx_a, "Goal in B")
    _create_main_goal(group, ws_c.id, ctx_c, "Goal in C")

    # Same tenant, another workspace: only B's goal comes back for B.
    result_b = group.execute_tool(
        tool_name="main_goal.query",
        params={"workspace_id": str(ws_b.id)},
        auth_context=ctx_a,
        api_key=VALID_API_KEY,
    )
    assert result_b.success is True, result_b.message
    assert [mg["content"] for mg in result_b.data["main_goals"]] == ["Goal in B"]

    # A's view must not leak B's goal (both live in tenant A).
    result_a = group.execute_tool(
        tool_name="main_goal.query",
        params={"workspace_id": str(ws_a.id)},
        auth_context=ctx_a,
        api_key=VALID_API_KEY,
    )
    assert [mg["content"] for mg in result_a.data["main_goals"]] == ["Goal in A"]

    # Cross-tenant: tenant A querying tenant C's workspace resolves nothing,
    # because the service filters on tenant_id as well as workspace_id.
    result_cross = group.execute_tool(
        tool_name="main_goal.query",
        params={"workspace_id": str(ws_c.id)},
        auth_context=ctx_a,
        api_key=VALID_API_KEY,
    )
    assert result_cross.success is True, result_cross.message
    assert result_cross.data == {"main_goals": [], "count": 0}

    # Positive control: the owning tenant still sees its own goal.
    result_c = group.execute_tool(
        tool_name="main_goal.query",
        params={"workspace_id": str(ws_c.id)},
        auth_context=ctx_c,
        api_key=VALID_API_KEY,
    )
    assert [mg["content"] for mg in result_c.data["main_goals"]] == ["Goal in C"]


# ---------------------------------------------------------------------------
# Role contract (E3)
# ---------------------------------------------------------------------------


def test_main_goal_query_is_registered_as_read_only():
    registry = ToolRegistry()
    assert registry._is_write_tool("main_goal.query") is False
    assert "main_goal.query" in _READ_ONLY_TOOL_NAMES


def test_viewer_member_can_query_own_workspace_via_dispatcher(
    e2e_userrole_viewer,
    e2e_api_key_viewer,
    e2e_workspace,
):
    """The read RBAC gate must admit a Viewer for their own workspace.

    Drives the real (unmocked) ``ToolRegistry`` so this is a gate assertion,
    not just a group-level unit check. The workspace holds no MainGoal yet, so
    the positive signal is ``success`` + the empty collection envelope; a
    PERMISSION_DENIED would fail the assertion.
    """
    result = ToolRegistry().dispatch_request(
        tool_name="main_goal.query",
        params={"workspace_id": str(e2e_workspace.id)},
        api_key=e2e_api_key_viewer,
    )

    assert result.success is True, result.message
    assert result.data == {"main_goals": [], "count": 0}


# ---------------------------------------------------------------------------
# Validation + schema
# ---------------------------------------------------------------------------


def test_main_goal_query_requires_workspace_id():
    tenant, _workspace = _tenant_and_workspace("I1097-V1", "W3")
    ctx = _ctx(tenant_id=tenant.id)

    result = MainGoalToolGroup().execute_tool(
        tool_name="main_goal.query",
        params={},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_main_goal_query_schema_requires_workspace_id_and_states_role_contract():
    schema = next(
        s
        for s in MainGoalToolGroup().get_tool_schemas()
        if s["name"] == "main_goal.query"
    )["inputSchema"]

    assert schema["required"] == ["workspace_id"]
    assert "workspace_id" in schema["properties"]

    description = next(
        s["description"]
        for s in MainGoalToolGroup().get_tool_schemas()
        if s["name"] == "main_goal.query"
    )
    # The E3 role contract is part of the published tool description, not just
    # an implementation detail.
    assert "member" in description
    assert "read-only" in description
    assert "tenant" in description
    assert "workspace" in description
