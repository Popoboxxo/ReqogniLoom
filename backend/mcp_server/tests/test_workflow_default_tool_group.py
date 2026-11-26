"""MCP ``workflow_default.*`` tool group (P1.8 / M-11).

The group exposes the *tenant-wide* global workflow defaults — the template a
workspace's non-customized definition inherits — over MCP, on the same Layer-2
facade (``application.workflow_facade.WorkflowFacade``) the REST
``/api/v1/workflow-defaults/`` surface calls. These tests pin four things:

1. the registry contract (nine tools, the 2-read/7-write split, and the
   workspace-scope classification both ratchets require);
2. the admin gate on reads *and* writes (mirror of REST's ``_require_admin``);
3. the graph payload and the CRUD lifecycle, including parity with REST's
   ``WorkflowDefinitionError`` mapping and the additive
   ``propagated_workspace_count``;
4. that a workspace-less write is admitted *because* it is on
   ``TENANT_SCOPED_WRITE_TOOLS`` — and denied when it is not (finding #4).

The API keys come from ``mcp_server/tests/conftest.py``; the calls go through
the real ``ToolRegistry.dispatch_request`` so the runtime gates (scope tier,
workspace scope, RBAC, handler) all run. ``Document``/``ccb_approval`` is
deliberately an unprovisioned pair in this fixture set (the REST smoke test uses
the same pair for that reason).
"""
from __future__ import annotations

import logging
from typing import Any
from unittest.mock import patch

import pytest

from mcp_server.tool_registry import ToolRegistry
from mcp_server.workspace_scope import (
    TENANT_SCOPED_READ_TOOLS,
    TENANT_SCOPED_WRITE_TOOLS,
)

pytestmark = pytest.mark.django_db

#: An item type/preset pair the e2e fixtures do not provision, so the
#: uninitialized-graph assertion is deterministic.
_ITEM_TYPE = "Document"
_PRESET = "ccb_approval"

READ_TOOLS = frozenset({"workflow_default.list", "workflow_default.get"})
WRITE_TOOLS = frozenset(
    {
        "workflow_default.initialize",
        "workflow_default.add_state",
        "workflow_default.update_state",
        "workflow_default.delete_state",
        "workflow_default.add_transition",
        "workflow_default.update_transition",
        "workflow_default.delete_transition",
    }
)
ALL_TOOLS = READ_TOOLS | WRITE_TOOLS


def _live_tools() -> dict[str, dict[str, Any]]:
    from mcp_server.management.commands.export_tool_manifest import build_manifest

    return {tool["name"]: tool for tool in build_manifest()["tools"]}


def _dispatch(tool: str, params: dict[str, Any], api_key: str):
    return ToolRegistry().dispatch_request(tool_name=tool, params=params, api_key=api_key)


def _call(tool: str, params: dict[str, Any], api_key: str) -> dict[str, Any]:
    """Dispatch *tool* and return the ``workflow_default`` graph."""
    result = _dispatch(tool, params, api_key)
    assert result.success, f"{tool} failed: {result.error_code}: {result.message}"
    return result.data["workflow_default"]


def _base(item_type: str = _ITEM_TYPE, preset: str = _PRESET) -> dict[str, Any]:
    return {"item_type": item_type, "preset": preset}


# ---------------------------------------------------------------------------
# Registry contract + scope classification
# ---------------------------------------------------------------------------


def test_the_group_publishes_nine_tools_with_the_documented_write_split() -> None:
    tools = _live_tools()
    published = {name for name in tools if name.startswith("workflow_default.")}
    assert published == ALL_TOOLS
    for name in READ_TOOLS:
        assert tools[name]["is_write"] is False, f"{name} must be a read tool"
    for name in WRITE_TOOLS:
        assert tools[name]["is_write"] is True, f"{name} must be a write tool"


def test_every_tool_is_classified_for_the_workspace_scope_ratchets() -> None:
    """No ``workspace_id`` exists in this group, so the allowlists carry it."""
    assert READ_TOOLS <= TENANT_SCOPED_READ_TOOLS
    assert WRITE_TOOLS <= TENANT_SCOPED_WRITE_TOOLS
    tools = _live_tools()
    for name in ALL_TOOLS:
        properties = (tools[name].get("inputSchema") or {}).get("properties") or {}
        assert "workspace_id" not in properties, (
            f"{name} must not accept a workspace_id — the global default is "
            "tenant-wide configuration, not a workspace resource"
        )


def test_every_tool_description_names_the_configuration_scope_and_the_rest_route() -> None:
    """A tool an agent can call must say what it configures and what it mirrors."""
    tools = _live_tools()
    for name in ALL_TOOLS:
        description = tools[name]["description"].lower()
        assert "tenant-wide" in description, name
        assert "admin only" in description, name
        assert "/api/v1/workflow-defaults/" in tools[name]["description"], name


# ---------------------------------------------------------------------------
# Admin gate
# ---------------------------------------------------------------------------


def test_a_non_admin_key_is_denied_on_read_and_write(
    e2e_api_key_member: str, e2e_userrole_member
) -> None:
    """The handler re-asserts admin exactly as REST's ``_require_admin`` does.

    The member's key is the legacy ``write`` (ADMIN-tier) scope, so the
    capability gate cannot be what refuses this: only the role check can.
    """
    read = _dispatch("workflow_default.get", _base(), e2e_api_key_member)
    assert not read.success
    assert read.error_code == "PERMISSION_DENIED", read.message

    write = _dispatch("workflow_default.initialize", _base(), e2e_api_key_member)
    assert not write.success
    assert write.error_code == "PERMISSION_DENIED", write.message


def test_every_catalogued_tool_denies_a_non_admin_caller(
    e2e_api_key_member: str, e2e_userrole_member
) -> None:
    """Catalogue-driven ratchet: no handler may skip the admin gate.

    Iterates the group's own ``_TOOL_MAP`` instead of a hand-picked pair, so a
    future tenth handler that does not run the shared ``_scope`` prelude (and
    therefore never reaches ``_admin_denied``) fails this test. Every call
    carries otherwise-valid parameters, so the refusal can only come from the
    role gate.
    """
    from mcp_server.tools.workflow_default import WorkflowDefaultToolGroup

    params_by_tool = {
        "workflow_default.list": {},
        "workflow_default.get": _base(),
        "workflow_default.initialize": _base(),
        "workflow_default.add_state": {**_base(), "name": "draft"},
        "workflow_default.update_state": {
            **_base(),
            "state": "draft",
            "new_name": "review",
        },
        "workflow_default.delete_state": {**_base(), "state": "draft"},
        "workflow_default.add_transition": {
            **_base(),
            "from_state": "draft",
            "to_state": "review",
        },
        "workflow_default.update_transition": {
            **_base(),
            "from_state": "draft",
            "to_state": "review",
        },
        "workflow_default.delete_transition": {
            **_base(),
            "from_state": "draft",
            "to_state": "review",
        },
    }
    tools = set(WorkflowDefaultToolGroup._TOOL_MAP)
    assert set(params_by_tool) == tools, (
        "a tool was added/removed without updating this ratchet's parameters"
    )
    assert tools == ALL_TOOLS

    for tool in sorted(tools):
        result = _dispatch(tool, params_by_tool[tool], e2e_api_key_member)
        assert not result.success, f"{tool} must be refused"
        assert result.error_code == "PERMISSION_DENIED", (tool, result.error_code)


def test_an_admin_key_succeeds(
    e2e_api_key_admin: str, e2e_userrole_admin
) -> None:
    result = _dispatch("workflow_default.list", {}, e2e_api_key_admin)
    assert result.success, result.message
    assert isinstance(result.data["workflow_defaults"], list)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def test_an_uninitialized_definition_is_the_empty_graph_not_an_error(
    e2e_api_key_admin: str, e2e_userrole_admin
) -> None:
    graph = _call("workflow_default.get", _base(), e2e_api_key_admin)
    assert graph["initialized"] is False
    assert graph["scope"] == "global"
    assert graph["item_type"] == _ITEM_TYPE
    assert graph["preset"] == _PRESET
    assert graph["initial_state"] is None
    assert graph["states"] == []
    assert graph["transitions"] == []
    assert graph["state_meta"] == {}
    assert graph["updated_at"] is None


def test_list_returns_the_stored_graphs_and_filters_by_item_type_and_preset(
    e2e_api_key_admin: str, e2e_userrole_admin
) -> None:
    api_key = e2e_api_key_admin
    _call("workflow_default.initialize", _base(), api_key)
    _call(
        "workflow_default.initialize",
        _base(_ITEM_TYPE, "custom_second_preset"),
        api_key,
    )
    _call("workflow_default.initialize", _base("Adr", _PRESET), api_key)
    _call("workflow_default.add_state", {**_base(), "name": "draft"}, api_key)

    all_rows = _dispatch("workflow_default.list", {}, api_key)
    assert all_rows.success, all_rows.message
    keys = {
        (row["item_type"], row["preset"])
        for row in all_rows.data["workflow_defaults"]
    }
    assert {(_ITEM_TYPE, _PRESET), (_ITEM_TYPE, "custom_second_preset"), ("Adr", _PRESET)} <= keys

    by_type = _dispatch(
        "workflow_default.list", {"item_type": _ITEM_TYPE}, api_key
    )
    assert by_type.success, by_type.message
    assert {
        row["item_type"] for row in by_type.data["workflow_defaults"]
    } == {_ITEM_TYPE}

    by_preset = _dispatch(
        "workflow_default.list",
        {"item_type": _ITEM_TYPE, "preset": "custom_second_preset"},
        api_key,
    )
    assert by_preset.success, by_preset.message
    rows = by_preset.data["workflow_defaults"]
    assert len(rows) == 1
    assert rows[0]["preset"] == "custom_second_preset"
    assert rows[0]["initialized"] is True


def test_get_returns_the_stored_graph(
    e2e_api_key_admin: str, e2e_userrole_admin
) -> None:
    api_key = e2e_api_key_admin
    _call("workflow_default.initialize", _base(), api_key)
    _call("workflow_default.add_state", {**_base(), "name": "draft"}, api_key)

    graph = _call("workflow_default.get", _base(), api_key)
    assert graph["initialized"] is True
    assert graph["states"] == ["draft"]
    assert graph["initial_state"] == "draft"
    # The transport boundary renders the row's datetime as an ISO string —
    # stdlib json.dumps would otherwise crash on it.
    assert isinstance(graph["updated_at"], str)


# ---------------------------------------------------------------------------
# Writes — full lifecycle
# ---------------------------------------------------------------------------


def test_the_write_lifecycle_returns_the_updated_graph_each_time(
    e2e_api_key_admin: str, e2e_userrole_admin
) -> None:
    api_key = e2e_api_key_admin

    created = _call("workflow_default.initialize", _base(), api_key)
    assert created["initialized"] is True
    assert created["states"] == []
    # initialize creates no derived rows yet, so the additive propagation
    # count is absent rather than 0.
    assert "propagated_workspace_count" not in created

    with_draft = _call(
        "workflow_default.add_state", {**_base(), "name": "draft"}, api_key
    )
    assert with_draft["states"] == ["draft"]
    assert with_draft["initial_state"] == "draft"
    assert with_draft["propagated_workspace_count"] == 0

    with_review = _call(
        "workflow_default.add_state", {**_base(), "name": "review"}, api_key
    )
    assert with_review["states"] == ["draft", "review"]

    with_edge = _call(
        "workflow_default.add_transition",
        {
            **_base(),
            "from_state": "draft",
            "to_state": "review",
            "allowed_roles": ["editor"],
            "requires_change_reason": True,
        },
        api_key,
    )
    assert with_edge["transitions"] == [
        {
            "from_state": "draft",
            "to_state": "review",
            # The store always keeps 'admin' in the role list.
            "allowed_roles": ["editor", "admin"],
            "requires_change_reason": True,
            "signature_gate": False,
        }
    ]
    assert with_edge["propagated_workspace_count"] == 0

    updated_edge = _call(
        "workflow_default.update_transition",
        {
            **_base(),
            "from_state": "draft",
            "to_state": "review",
            "allowed_roles": ["approver"],
            "signature_gate": True,
        },
        api_key,
    )
    assert updated_edge["transitions"] == [
        {
            "from_state": "draft",
            "to_state": "review",
            "allowed_roles": ["approver", "admin"],
            # Omitted on the update — the REST handler passes it through
            # unchanged, and this tool mirrors that.
            "requires_change_reason": True,
            "signature_gate": True,
        }
    ]

    renamed = _call(
        "workflow_default.update_state",
        {**_base(), "state": "review", "new_name": "in_review"},
        api_key,
    )
    assert renamed["states"] == ["draft", "in_review"]
    assert renamed["transitions"][0]["from_state"] == "draft"
    assert renamed["transitions"][0]["to_state"] == "in_review"

    frozen = _call(
        "workflow_default.update_state",
        {**_base(), "state": "in_review", "freeze_on_enter": True},
        api_key,
    )
    assert frozen["state_meta"]["in_review"]["freeze_on_enter"] is True
    assert frozen["propagated_workspace_count"] == 0

    without_edge = _call(
        "workflow_default.delete_transition",
        {**_base(), "from_state": "draft", "to_state": "in_review"},
        api_key,
    )
    assert without_edge["transitions"] == []

    without_state = _call(
        "workflow_default.delete_state", {**_base(), "state": "in_review"}, api_key
    )
    assert without_state["states"] == ["draft"]
    assert without_state["propagated_workspace_count"] == 0


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def test_an_unknown_item_type_is_not_found(
    e2e_api_key_admin: str, e2e_userrole_admin
) -> None:
    """R-F2-2 parity: a typo must not look like an uninitialised workflow."""
    api_key = e2e_api_key_admin
    for tool in (
        "workflow_default.get",
        "workflow_default.initialize",
        "workflow_default.add_state",
    ):
        result = _dispatch(tool, {**_base("NoSuchType", _PRESET), "name": "x"}, api_key)
        assert not result.success, tool
        assert result.error_code == "NOT_FOUND", (tool, result.error_code)


def test_a_duplicate_state_is_a_validation_error(
    e2e_api_key_admin: str, e2e_userrole_admin
) -> None:
    api_key = e2e_api_key_admin
    _call("workflow_default.initialize", _base(), api_key)
    _call("workflow_default.add_state", {**_base(), "name": "draft"}, api_key)

    duplicate = _dispatch(
        "workflow_default.add_state", {**_base(), "name": "draft"}, api_key
    )
    assert not duplicate.success
    assert duplicate.error_code == "VALIDATION_ERROR", duplicate.message


def test_a_preset_wider_than_the_column_is_a_validation_error(
    e2e_api_key_admin: str, e2e_userrole_admin
) -> None:
    """A >32-character preset would hit the column and mask as INTERNAL_ERROR."""
    result = _dispatch(
        "workflow_default.get", _base(_ITEM_TYPE, "x" * 33), e2e_api_key_admin
    )
    assert not result.success
    assert result.error_code == "VALIDATION_ERROR", result.message


def test_a_non_string_allowed_role_is_a_validation_error(
    e2e_api_key_admin: str, e2e_userrole_admin
) -> None:
    """A wrongly typed role used to raise AttributeError in the store (masked)."""
    result = _dispatch(
        "workflow_default.add_transition",
        {
            **_base(),
            "from_state": "draft",
            "to_state": "review",
            "allowed_roles": ["editor", 5],
        },
        e2e_api_key_admin,
    )
    assert not result.success
    assert result.error_code == "VALIDATION_ERROR", result.message


def test_deleting_a_referenced_state_is_a_conflict(
    e2e_api_key_admin: str, e2e_userrole_admin
) -> None:
    api_key = e2e_api_key_admin
    _call("workflow_default.initialize", _base(), api_key)
    _call("workflow_default.add_state", {**_base(), "name": "draft"}, api_key)
    _call("workflow_default.add_state", {**_base(), "name": "review"}, api_key)
    _call(
        "workflow_default.add_transition",
        {**_base(), "from_state": "draft", "to_state": "review"},
        api_key,
    )

    blocked = _dispatch(
        "workflow_default.delete_state", {**_base(), "state": "review"}, api_key
    )
    assert not blocked.success
    assert blocked.error_code == "CONFLICT", blocked.message
    # Nothing changed.
    graph = _call("workflow_default.get", _base(), api_key)
    assert graph["states"] == ["draft", "review"]
    assert len(graph["transitions"]) == 1


def test_re_initializing_an_existing_pair_is_a_conflict(
    e2e_api_key_admin: str, e2e_userrole_admin
) -> None:
    api_key = e2e_api_key_admin
    _call("workflow_default.initialize", _base(), api_key)

    again = _dispatch("workflow_default.initialize", _base(), api_key)
    assert not again.success
    assert again.error_code == "CONFLICT", again.message


def test_an_unexpected_service_failure_is_masked_and_logged(
    e2e_api_key_admin: str, e2e_userrole_admin, caplog
) -> None:
    """CWE-209: the cause is logged, the caller sees a static message."""
    with (
        patch(
            "mcp_server.tools.workflow_default.WorkflowFacade.list_global_definitions",
            side_effect=RuntimeError("boom: connection secret-dsn"),
        ),
        caplog.at_level(logging.ERROR, logger="mcp_server.tools.workflow_default"),
    ):
        result = _dispatch("workflow_default.list", {}, e2e_api_key_admin)

    assert not result.success
    assert result.error_code == "INTERNAL_ERROR", result.message
    assert "secret-dsn" not in (result.message or "")
    assert "boom" not in (result.message or "")
    records = [
        record
        for record in caplog.records
        if record.name == "mcp_server.tools.workflow_default"
        and record.levelno >= logging.ERROR
    ]
    assert records, "the masked failure must leave a log record"
    assert any("workflow_default tool failed" in record.getMessage() for record in records)


def test_the_guard_maps_domain_errors() -> None:
    """The error mapping is the local twin of REST's ``_map_workflow_error``.

    Layering (that this module does not import the REST layer) is pinned by
    ``rest_api/tests/test_architecture.py``, not here.
    """
    from application.base import OptimisticLockError
    from mcp_server.tools.workflow_default import WorkflowDefaultToolGroup
    from workflow.services import StateReferencedError, WorkflowDefinitionError

    group = WorkflowDefaultToolGroup()

    def _raiser(exc: BaseException):
        def _call_it():
            raise exc

        return _call_it

    assert (
        group._guard(_raiser(StateReferencedError("a", ["a -> b"]))).error_code
        == "CONFLICT"
    )
    assert (
        group._guard(
            _raiser(WorkflowDefinitionError("Global definition already initialized"))
        ).error_code
        == "CONFLICT"
    )
    assert (
        group._guard(_raiser(WorkflowDefinitionError("Unknown state 'x'"))).error_code
        == "VALIDATION_ERROR"
    )
    assert (
        group._guard(_raiser(OptimisticLockError("stale version"))).error_code
        == "CONFLICT"
    )


# ---------------------------------------------------------------------------
# Workspace scope (finding #4 / P1.2)
# ---------------------------------------------------------------------------


def test_a_workspace_less_write_is_admitted_only_by_the_tenant_allowlist(
    e2e_api_key_admin: str, e2e_userrole_admin
) -> None:
    """The P1.2 fail-closed gate denies an unscoped write unless allowlisted.

    Removing ``workflow_default.initialize`` from
    ``TENANT_SCOPED_WRITE_TOOLS`` must turn the same call into a
    ``PERMISSION_DENIED`` — which is what proves the allowlist entry, and not
    some other path, is what admits it.
    """
    api_key = e2e_api_key_admin
    without_allowlist = frozenset(
        TENANT_SCOPED_WRITE_TOOLS - {"workflow_default.initialize"}
    )
    with patch(
        "mcp_server.workspace_scope.TENANT_SCOPED_WRITE_TOOLS", without_allowlist
    ):
        denied = _dispatch("workflow_default.initialize", _base(), api_key)
    assert not denied.success
    assert denied.error_code == "PERMISSION_DENIED", denied.message

    admitted = _dispatch("workflow_default.initialize", _base(), api_key)
    assert admitted.success, admitted.message
