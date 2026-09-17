"""Tests for GitHub issue #346 finding 3: the incomplete ``goal.*`` lifecycle.

Three gaps this covers:

1. ``goal.update`` / ``goal.outdate`` / ``goal.reactivate`` did not exist at
   all, so an MCP client could create and archive a Goal but never edit or
   restore one.
2. ``goal.delete`` is a soft-archive via a workflow transition, not a hard
   delete, and is only reachable from the states the workspace's Goal workflow
   defines an edge to 'Archiviert' from — undocumented, so callers could not
   tell a 400 "wrong state" from a broken tool.
3. ``goal.transition`` answered an unreachable ``target_state`` with a bare
   400 that never named the states that ARE reachable.

Style mirrors ``test_goal_query_delete.py``: drives the real ``GoalService``
through the MCP tool group against the DB, with a provisioned ``goal_default``
workflow, rather than mocking the service away.
"""
from __future__ import annotations

import uuid

import pytest

from mcp_server.tool_registry import ToolRegistry
from mcp_server.tools.goals import GoalToolGroup
from auth_tenancy.context import AuthContext, AuthMethod
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
    tenant = Tenant.objects.create(name=tenant_name)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, **workspace_kwargs)
    finally:
        TenantContext.clear_tenant()
    return tenant, workspace


def _provision(workspace, *, preset: str = "goal_default", item_type: str = "Goal") -> None:
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


def _workspace_with_goal(name: str, *, title: str = "Goal A", description: str = ""):
    """Provision a workspace with the goal_default workflow and one draft Goal."""
    tenant, workspace = _tenant_and_workspace(name, name=name, goals_enabled=True)
    _provision(workspace)
    ctx = _ctx(tenant_id=tenant.id)
    group = GoalToolGroup()
    created = group.execute_tool(
        tool_name="goal.create",
        params={
            "workspace_id": str(workspace.id),
            "title": title,
            "description": description,
        },
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert created.success is True, created.message
    return group, ctx, workspace, created.data


# ---------------------------------------------------------------------------
# goal.update
# ---------------------------------------------------------------------------


def test_goal_update_appends_a_new_lineage_version():
    """Goals are immutable rows — an update appends v2 to the same lineage."""
    group, ctx, _ws, created = _workspace_with_goal("I346-U1", title="Goal A")

    result = group.execute_tool(
        tool_name="goal.update",
        params={"goal_id": created["id"], "title": "Goal A revised"},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    assert result.success is True, result.message
    assert result.data["title"] == "Goal A revised"
    assert result.data["lineage_id"] == created["lineage_id"]
    assert result.data["sequence_number"] == created["sequence_number"] + 1
    assert result.data["id"] != created["id"]
    # A new version always starts as a draft and must be approved again.
    assert result.data["status"] == "Entwurf"

    # The addressed version is untouched (that is what makes it an audit trail).
    previous = group.execute_tool(
        tool_name="goal.read",
        params={"goal_id": created["id"]},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert previous.data["title"] == "Goal A"


def test_goal_update_carries_over_omitted_fields():
    group, ctx, _ws, created = _workspace_with_goal(
        "I346-U2", title="Goal A", description="Original description"
    )

    result = group.execute_tool(
        tool_name="goal.update",
        params={"goal_id": created["id"], "title": "Only the title changed"},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    assert result.success is True, result.message
    assert result.data["description"] == "Original description"


def test_goal_update_rejects_status_changes():
    """Mirrors GenericCrudToolGroup._handle_update (#83 Bug 2): the workflow
    engine is the only authority over ``status``."""
    group, ctx, _ws, created = _workspace_with_goal("I346-U3")

    result = group.execute_tool(
        tool_name="goal.update",
        params={"goal_id": created["id"], "status": "Freigegeben"},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "goal.transition" in (result.message or "")


def test_goal_update_unknown_id_returns_not_found():
    tenant, _workspace = _tenant_and_workspace("I346-U4", name="I346-U4")
    group = GoalToolGroup()

    result = group.execute_tool(
        tool_name="goal.update",
        params={"goal_id": str(uuid.uuid4()), "title": "x"},
        auth_context=_ctx(tenant_id=tenant.id),
        api_key=VALID_API_KEY,
    )

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_goal_update_requires_write_permission():
    group, _admin_ctx, workspace, created = _workspace_with_goal("I346-U5")
    viewer_ctx = _ctx(tenant_id=workspace.tenant_id, roles=("viewer",))

    result = group.execute_tool(
        tool_name="goal.update",
        params={"goal_id": created["id"], "title": "nope"},
        auth_context=viewer_ctx,
        api_key=VALID_API_KEY,
    )

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# goal.outdate / goal.reactivate
# ---------------------------------------------------------------------------


def test_goal_outdate_archives_like_goal_delete():
    group, ctx, _ws, created = _workspace_with_goal("I346-O1")

    result = group.execute_tool(
        tool_name="goal.outdate",
        params={"goal_id": created["id"]},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    assert result.success is True, result.message
    # NOT the generic "outdated" escape-hatch state: that one is foreign to the
    # Goal state machine and would slip past the Archiviert list filters.
    assert result.data["status"] == "Archiviert"


def test_goal_outdate_accepts_the_generic_id_parameter_alias():
    group, ctx, _ws, created = _workspace_with_goal("I346-O2")

    result = group.execute_tool(
        tool_name="goal.outdate",
        params={"id": created["id"], "reason": "obsolete"},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    assert result.success is True, result.message
    assert result.data["status"] == "Archiviert"


def test_goal_outdate_requires_approver_role():
    group, _admin_ctx, workspace, created = _workspace_with_goal("I346-O3")
    editor_ctx = _ctx(tenant_id=workspace.tenant_id, roles=("editor",))

    result = group.execute_tool(
        tool_name="goal.outdate",
        params={"goal_id": created["id"]},
        auth_context=editor_ctx,
        api_key=VALID_API_KEY,
    )

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


def test_goal_reactivate_restores_an_archived_goal_as_a_draft():
    group, ctx, _ws, created = _workspace_with_goal("I346-R1")
    group.execute_tool(
        tool_name="goal.transition",
        params={
            "goal_id": created["id"],
            "target_state": "Freigegeben",
            "change_reason": "Approved.",
        },
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    archived = group.execute_tool(
        tool_name="goal.delete",
        params={"goal_id": created["id"]},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert archived.data["status"] == "Archiviert"

    result = group.execute_tool(
        tool_name="goal.reactivate",
        params={"goal_id": created["id"]},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    assert result.success is True, result.message
    # Deliberately NOT back to Freigegeben: only approved versions feed
    # MainGoal aggregation, so a restored Goal must be re-approved.
    assert result.data["status"] == "Entwurf"


def test_goal_reactivate_on_a_draft_lists_the_reachable_states():
    """The reverse direction of finding 3: an impossible restore explains
    itself instead of returning a bare 400."""
    group, ctx, _ws, created = _workspace_with_goal("I346-R2")

    result = group.execute_tool(
        tool_name="goal.reactivate",
        params={"goal_id": created["id"]},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert result.details is not None
    assert result.details["current_state"] == "Entwurf"
    assert "Freigegeben" in result.details["valid_target_states"]


def test_goal_reactivate_unknown_id_returns_not_found():
    tenant, _workspace = _tenant_and_workspace("I346-R3", name="I346-R3")
    group = GoalToolGroup()

    result = group.execute_tool(
        tool_name="goal.reactivate",
        params={"goal_id": str(uuid.uuid4())},
        auth_context=_ctx(tenant_id=tenant.id),
        api_key=VALID_API_KEY,
    )

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# goal.transition — the 400 must list the valid target states (finding 3)
# ---------------------------------------------------------------------------


def test_goal_transition_invalid_target_lists_valid_states_in_details():
    group, ctx, _ws, created = _workspace_with_goal("I346-T1")

    result = group.execute_tool(
        tool_name="goal.transition",
        params={"goal_id": created["id"], "target_state": "approved"},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert result.details is not None
    assert result.details["current_state"] == "Entwurf"
    # goal_default: Entwurf -> Freigegeben and Entwurf -> Archiviert.
    assert sorted(result.details["valid_target_states"]) == [
        "Archiviert",
        "Freigegeben",
    ]


def test_goal_transition_invalid_target_names_valid_states_in_the_message():
    """The message matters too — many MCP clients only surface ``message``."""
    group, ctx, _ws, created = _workspace_with_goal("I346-T2")

    result = group.execute_tool(
        tool_name="goal.transition",
        params={"goal_id": created["id"], "target_state": "Erledigt"},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    assert result.success is False
    message = result.message or ""
    assert "Entwurf" in message
    assert "Freigegeben" in message
    assert "Archiviert" in message


def test_goal_transition_missing_target_state_still_validates():
    group, ctx, _ws, created = _workspace_with_goal("I346-T3")

    result = group.execute_tool(
        tool_name="goal.transition",
        params={"goal_id": created["id"]},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "target_state" in (result.message or "")


# ---------------------------------------------------------------------------
# Registration, RBAC gate and tool discovery text
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool_name", ["goal.update", "goal.outdate", "goal.reactivate"]
)
def test_new_goal_lifecycle_tools_are_registered(tool_name):
    registry = ToolRegistry()
    registry._ensure_groups()
    names = {
        schema["name"]
        for group in registry._groups.values()
        for schema in group.get_tool_schemas()
    }
    assert tool_name in names


@pytest.mark.parametrize(
    "tool_name", ["goal.update", "goal.outdate", "goal.reactivate"]
)
def test_new_goal_lifecycle_tools_are_write_protected(tool_name):
    registry = ToolRegistry()
    assert registry._is_write_tool(tool_name) is True


def test_goal_delete_description_documents_the_soft_archive_semantics():
    """Finding 3 bullet 2: the archive-not-delete semantics, the reachable
    source states and the invalid-state error must be discoverable from
    ``tools/list`` — i.e. from the schema description, not just a Python
    docstring the MCP client never sees.
    """
    schema = next(
        s for s in GoalToolGroup().get_tool_schemas() if s["name"] == "goal.delete"
    )
    description = schema["description"]

    assert "NOT a hard" in description
    assert "Archiviert" in description
    assert "Entwurf" in description
    assert "Freigegeben" in description
    assert "VALIDATION_ERROR" in description
    assert "goal.reactivate" in description
