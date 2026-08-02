"""Regression tests for issue #270 (MEDIUM batch: Goal/MainGoal MCP details).

Unlike ``test_goal_tools.py`` (registration smoke tests + mocked services),
these tests drive the real ``GoalService``/``MainGoalService`` against the DB
through the MCP tool groups, mirroring the request-factory + real-fixtures
style of ``rest_api/tests/test_goal_views.py``. Each test pins one of the five
findings reported in issue #270.
"""
from __future__ import annotations

import uuid

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tools.goals import GoalToolGroup, MainGoalToolGroup
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


def _tenant_and_workspace(tenant_name: str, **workspace_kwargs):
    """Create Tenant + Workspace under an active TenantContext."""
    tenant = Tenant.objects.create(name=tenant_name)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, **workspace_kwargs)
    finally:
        TenantContext.clear_tenant()
    return tenant, workspace


def _provision(workspace, *, preset: str, item_type: str) -> None:
    from workflow.services import create_default_workflow

    TenantContext.set_tenant(workspace.tenant_id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset=preset,
            item_type=item_type,
            tenant_id=workspace.tenant_id,
        )
    finally:
        TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# Finding 1 — goal.transition names the wrong preset in the change_reason error
# ---------------------------------------------------------------------------


def test_transition_without_change_reason_names_actual_preset():
    tenant, workspace = _tenant_and_workspace("I270-T1", name="W1", goals_enabled=True)
    _provision(workspace, preset="goal_default", item_type="Goal")
    ctx = _ctx(tenant_id=tenant.id)
    group = GoalToolGroup()

    created = group.execute_tool(
        tool_name="goal.create",
        params={"workspace_id": str(workspace.id), "title": "G1"},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert created.success is True

    result = group.execute_tool(
        tool_name="goal.transition",
        params={"goal_id": created.data["id"], "target_state": "Freigegeben"},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    assert result.success is False
    message = result.message or ""
    assert "change_reason" in message
    # The workspace has no explicit preset -> tier "minimal". Claiming
    # "extended preset" here sends users hunting for a setting they never made.
    assert "extended preset" not in message
    assert "minimal preset" in message


# ---------------------------------------------------------------------------
# Finding 2 — main_goal.read must return the currently valid version
# ---------------------------------------------------------------------------


def test_main_goal_read_returns_approved_version():
    tenant, workspace = _tenant_and_workspace("I270-T2", name="W2", goals_enabled=True)
    _provision(workspace, preset="main_goal_default", item_type="MainGoal")
    ctx = _ctx(tenant_id=tenant.id)
    group = MainGoalToolGroup()

    first = group.execute_tool(
        tool_name="main_goal.create_manual",
        params={"workspace_id": str(workspace.id), "content": "v1 content"},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert first.success is True

    approved = group.execute_tool(
        tool_name="main_goal.approve",
        params={
            "main_goal_id": first.data["main_goal"]["id"],
            "change_reason": "Approved.",
        },
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert approved.success is True, approved.message
    # The approve result must already carry the full object, not just
    # {id, sequence_number, status} — clients render it directly.
    assert approved.data["main_goal"]["content"] == "v1 content"
    assert approved.data["main_goal"]["status"] == "Freigegeben"

    versions = group.execute_tool(
        tool_name="main_goal.list_versions",
        params={"workspace_id": str(workspace.id)},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert len(versions.data["versions"]) == 1

    read = group.execute_tool(
        tool_name="main_goal.read",
        params={"workspace_id": str(workspace.id)},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert read.success is True
    assert read.data["main_goal"] is not None
    assert read.data["main_goal"]["id"] == first.data["main_goal"]["id"]
    assert read.data["main_goal"]["content"] == "v1 content"
    assert read.data["main_goal"]["status"] == "Freigegeben"


def test_main_goal_read_without_approved_version_explains_why():
    """A draft-only chain has no valid MainGoal — say so instead of nothing."""
    tenant, workspace = _tenant_and_workspace("I270-T2b", name="W2b", goals_enabled=True)
    ctx = _ctx(tenant_id=tenant.id)
    group = MainGoalToolGroup()

    group.execute_tool(
        tool_name="main_goal.create_manual",
        params={"workspace_id": str(workspace.id), "content": "draft only"},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    read = group.execute_tool(
        tool_name="main_goal.read",
        params={"workspace_id": str(workspace.id)},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert read.success is True
    assert read.data["main_goal"] is None
    assert "Freigegeben" in read.data["reason"]
    assert "1 version(s)" in read.data["reason"]


# ---------------------------------------------------------------------------
# Finding 3 — main_goal.create_manual must return the persisted identity
# ---------------------------------------------------------------------------


def test_main_goal_create_manual_returns_identity():
    tenant, workspace = _tenant_and_workspace("I270-T3", name="W3", goals_enabled=True)
    ctx = _ctx(tenant_id=tenant.id)
    group = MainGoalToolGroup()

    result = group.execute_tool(
        tool_name="main_goal.create_manual",
        params={"workspace_id": str(workspace.id), "content": "Be the best."},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    assert result.success is True
    # The payload must be nested: a top-level "content" key collides with the
    # MCP result envelope's own "content" field, which is what reduced the
    # response to a bare echo of the MainGoal text.
    assert set(result.data) == {"main_goal"}
    payload = result.data["main_goal"]
    assert uuid.UUID(payload["id"])
    assert payload["sequence_number"] == 1
    assert payload["content"] == "Be the best."
    assert payload["source"] == "manual"
    assert payload["status"] == "Entwurf"


def test_main_goal_create_manual_over_jsonrpc_returns_identity(
    admin_client, e2e_workspace, e2e_userrole_admin
):
    """Full HTTP/JSON-RPC pipeline: the id must survive MCP serialization."""
    import json

    from mcp_server.tests.helpers import extract_result, post_mcp
    from persistence.middleware import clear_request_tenant, set_request_tenant

    set_request_tenant(e2e_workspace.tenant_id)
    try:
        e2e_workspace.goals_enabled = True
        e2e_workspace.save(update_fields=["goals_enabled"])
    finally:
        clear_request_tenant()

    response = post_mcp(
        admin_client,
        "tools/call",
        {
            "name": "main_goal.create_manual",
            "arguments": {
                "workspace_id": str(e2e_workspace.id),
                "content": "Ship the thing.",
            },
        },
    )

    assert response.status_code == 200, response.content
    result = extract_result(response)
    assert result.get("isError") is not True, result
    payload = json.loads(result["content"][0]["text"])["main_goal"]
    assert uuid.UUID(payload["id"])
    assert payload["content"] == "Ship the thing."
    assert payload["sequence_number"] == 1


# ---------------------------------------------------------------------------
# Finding 4 — goal.create_version keeps the lineage UUID stable
# ---------------------------------------------------------------------------


def test_goal_create_version_returns_stable_lineage_id():
    tenant, workspace = _tenant_and_workspace("I270-T4", name="W4", goals_enabled=True)
    ctx = _ctx(tenant_id=tenant.id)
    group = GoalToolGroup()

    created = group.execute_tool(
        tool_name="goal.create",
        params={"workspace_id": str(workspace.id), "title": "v1"},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    lineage_id = created.data["lineage_id"]
    assert lineage_id != created.data["id"]

    second = group.execute_tool(
        tool_name="goal.create_version",
        params={
            "workspace_id": str(workspace.id),
            "lineage_id": lineage_id,
            "title": "v2",
        },
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    assert second.success is True
    assert second.data["lineage_id"] == lineage_id
    assert second.data["id"] != created.data["id"]
    assert second.data["sequence_number"] == 2

    versions = group.execute_tool(
        tool_name="goal.list_versions",
        params={"lineage_id": second.data["lineage_id"]},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert [v["sequence_number"] for v in versions.data["versions"]] == [1, 2]


def test_goal_create_version_rejects_a_goal_id_as_lineage_id():
    """Passing a version id where a lineage id belongs must fail loudly.

    It used to start a second lineage keyed by that version id, which is how a
    response's ``lineage_id`` could end up equal to the previous version's id.
    """
    tenant, workspace = _tenant_and_workspace("I270-T4b", name="W4b", goals_enabled=True)
    ctx = _ctx(tenant_id=tenant.id)
    group = GoalToolGroup()

    created = group.execute_tool(
        tool_name="goal.create",
        params={"workspace_id": str(workspace.id), "title": "v1"},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    result = group.execute_tool(
        tool_name="goal.create_version",
        params={
            "workspace_id": str(workspace.id),
            "lineage_id": created.data["id"],  # a version id, not a lineage id
            "title": "v2",
        },
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    assert result.success is False
    assert result.error_code == "NOT_FOUND"
    assert created.data["lineage_id"] in (result.message or "")


def test_goal_create_version_rejects_unknown_lineage_id():
    tenant, workspace = _tenant_and_workspace("I270-T4c", name="W4c", goals_enabled=True)
    ctx = _ctx(tenant_id=tenant.id)
    group = GoalToolGroup()

    result = group.execute_tool(
        tool_name="goal.create_version",
        params={
            "workspace_id": str(workspace.id),
            "lineage_id": str(uuid.uuid4()),
            "title": "orphan",
        },
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Finding 5 — target_state must be enumerated in the tool schema
# ---------------------------------------------------------------------------


def _schema(group, tool_name: str) -> dict:
    return next(s for s in group.get_tool_schemas() if s["name"] == tool_name)


def test_goal_transition_schema_enumerates_target_states():
    schema = _schema(GoalToolGroup(), "goal.transition")
    target_state = schema["inputSchema"]["properties"]["target_state"]
    assert target_state.get("enum") == ["Entwurf", "Freigegeben", "Archiviert"]


def test_goal_transition_enum_matches_the_preset_schema():
    """The enum must stay derived from the workflow preset (single source)."""
    from workflow.definition_store import PRESET_SCHEMAS

    schema = _schema(GoalToolGroup(), "goal.transition")
    assert schema["inputSchema"]["properties"]["target_state"]["enum"] == list(
        PRESET_SCHEMAS["goal_default"]["states"]
    )


def test_main_goal_approve_schema_documents_the_target_state():
    """main_goal.approve takes no target_state; its states must be documented."""
    schema = _schema(MainGoalToolGroup(), "main_goal.approve")
    assert "target_state" not in schema["inputSchema"]["properties"]
    assert "Freigegeben" in schema["description"]
