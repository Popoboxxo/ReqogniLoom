"""MCP ``create_form_definition.*`` tool group — create-dialog form (#1263).

The two handlers are thin wrappers over ``CreateFormConfigService``; these tests
pin the published schemas, the argument normalisation, the delegation contract
and the classification gates the rest of the MCP suite depends on (the
fail-closed read/write split and the workspace-scope coverage entry).

Service calls are patched where a real row is irrelevant; the *wiring* checks
(group registration, read/write classification, workspace-scope coverage) run
against the live registry.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from auth_tenancy.context import AuthContext, AuthMethod


@pytest.fixture
def group():
    from mcp_server.tools.create_form_config import CreateFormConfigToolGroup

    return CreateFormConfigToolGroup()


@pytest.fixture
def ctx() -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("editor",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _call(group, name, params, ctx):
    return group.execute_tool(
        tool_name=name,
        params=params,
        auth_context=ctx,
        api_key="reqlo_test_key",
    )


def _service_patch(method: str):
    return patch(
        f"application.create_form_config_service.CreateFormConfigService.{method}",
        return_value={"scope": "user", "item_type": "Requirement", "fields": []},
    )


# ---------------------------------------------------------------------------
# Published surface
# ---------------------------------------------------------------------------


def test_group_publishes_exactly_four_tools(group) -> None:
    names = {schema["name"] for schema in group._TOOL_SCHEMAS}
    assert names == {
        "create_form_definition.get",
        "create_form_definition.set",
        "create_form_definition.export",
        "create_form_definition.import",
    }
    assert set(group._TOOL_MAP) == names
    for handler in group._TOOL_MAP.values():
        assert hasattr(group, handler)


def test_get_schema_offers_the_effective_and_per_level_scopes(group) -> None:
    schema = next(
        s for s in group._TOOL_SCHEMAS if s["name"] == "create_form_definition.get"
    )
    enum = schema["inputSchema"]["properties"]["scope"]["enum"]
    assert enum == ["effective", "user", "workspace", "global", "default"]
    assert "required" not in schema["inputSchema"]


def test_set_schema_requires_scope_item_type_and_fields(group) -> None:
    schema = next(
        s for s in group._TOOL_SCHEMAS if s["name"] == "create_form_definition.set"
    )
    assert schema["inputSchema"]["required"] == ["scope", "item_type", "fields"]
    assert schema["inputSchema"]["properties"]["scope"]["enum"] == [
        "user",
        "workspace",
        "global",
    ]


# ---------------------------------------------------------------------------
# Registry classification
# ---------------------------------------------------------------------------


def test_group_is_registered_and_split_read_write(db) -> None:
    from mcp_server.tool_registry import ToolRegistry

    registry = ToolRegistry()
    registry._ensure_groups()
    assert "create_form_definition" in registry._groups
    assert registry._is_write_tool("create_form_definition.get") is False
    assert registry._is_write_tool("create_form_definition.set") is True
    assert registry._is_write_tool("create_form_definition.export") is False
    assert registry._is_write_tool("create_form_definition.import") is True


def test_reads_are_classified_for_workspace_scope_coverage() -> None:
    """The coverage ratchet in test_mcp_workspace_scope.py needs these entries."""
    from mcp_server.workspace_scope import TENANT_SCOPED_READ_TOOLS

    assert "create_form_definition.get" in TENANT_SCOPED_READ_TOOLS
    assert "create_form_definition.export" in TENANT_SCOPED_READ_TOOLS


# ---------------------------------------------------------------------------
# Argument normalisation + delegation
# ---------------------------------------------------------------------------


def test_get_effective_delegates_with_item_type_and_workspace(group, ctx) -> None:
    workspace_id = uuid.uuid4()
    with _service_patch("get_config") as patched:
        result = _call(
            group,
            "create_form_definition.get",
            {"scope": "effective", "item_type": " Requirement ",
             "workspace_id": str(workspace_id)},
            ctx,
        )
    assert result.success
    patched.assert_called_once()
    kwargs = patched.call_args.kwargs
    assert kwargs["item_type"] == "Requirement"
    assert kwargs["workspace_id"] == workspace_id


def test_get_effective_requires_item_type(group, ctx) -> None:
    result = _call(group, "create_form_definition.get", {"scope": "effective"}, ctx)
    assert not result.success


def test_get_unknown_scope_is_rejected(group, ctx) -> None:
    result = _call(
        group, "create_form_definition.get", {"scope": "tenant"}, ctx
    )
    assert not result.success


def test_set_delegates_one_level(group, ctx) -> None:
    workspace_id = uuid.uuid4()
    with _service_patch("set_config") as patched:
        result = _call(
            group,
            "create_form_definition.set",
            {
                "scope": "workspace",
                "item_type": "Requirement",
                "fields": [{"field_key": "title", "visible": True}],
                "workspace_id": str(workspace_id),
            },
            ctx,
        )
    assert result.success
    patched.assert_called_once()
    kwargs = patched.call_args.kwargs
    assert kwargs["scope"] == "workspace"
    assert kwargs["item_type"] == "Requirement"
    assert kwargs["fields"] == [{"field_key": "title", "visible": True}]


def test_set_workspace_requires_workspace_id(group, ctx) -> None:
    result = _call(
        group,
        "create_form_definition.set",
        {"scope": "workspace", "item_type": "Requirement", "fields": []},
        ctx,
    )
    assert not result.success


def test_set_user_rejects_a_workspace_id(group, ctx) -> None:
    result = _call(
        group,
        "create_form_definition.set",
        {
            "scope": "user",
            "item_type": "Requirement",
            "fields": [],
            "workspace_id": str(uuid.uuid4()),
        },
        ctx,
    )
    assert not result.success


def test_export_delegates_one_level(group, ctx) -> None:
    with _service_patch("export_config") as patched:
        result = _call(
            group,
            "create_form_definition.export",
            {"scope": "global", "item_type": "Requirement"},
            ctx,
        )
    assert result.success
    assert patched.call_args.kwargs["scope"] == "global"


def test_import_requires_a_document(group, ctx) -> None:
    result = _call(
        group,
        "create_form_definition.import",
        {"scope": "user", "item_type": "Requirement"},
        ctx,
    )
    assert not result.success


def test_import_delegates_the_document(group, ctx) -> None:
    document = {"schema_version": 1, "fields": []}
    with _service_patch("import_config") as patched:
        result = _call(
            group,
            "create_form_definition.import",
            {"scope": "user", "item_type": "Requirement", "document": document},
            ctx,
        )
    assert result.success
    assert patched.call_args.kwargs["payload"] == document


def test_set_fields_null_resets(group, ctx) -> None:
    with _service_patch("set_config") as patched:
        result = _call(
            group,
            "create_form_definition.set",
            {"scope": "user", "item_type": "Requirement", "fields": None},
            ctx,
        )
    assert result.success
    assert patched.call_args.kwargs["fields"] is None
