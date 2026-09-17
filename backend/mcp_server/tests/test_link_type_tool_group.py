"""MCP link_type.* tool group and the create_link schema change."""
from __future__ import annotations

import json
import uuid

import pytest

from link_types.builtin import builtin_definition


@pytest.fixture
def group():
    from mcp_server.tools.link_type import LinkTypeToolGroup

    return LinkTypeToolGroup()


@pytest.fixture
def env(db):
    from auth_tenancy.context import AuthContext, AuthMethod
    from link_types.workspace_store import provision_workspace_link_types
    from persistence.models import Tenant, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(name="mcp-link-type")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="ws")
    provision_workspace_link_types(workspace_id=ws.id, tenant_id=tenant.id)
    ctx = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        workspace_id=ws.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    yield {"workspace": ws, "ctx": ctx}
    TenantContext.clear_tenant()


def test_the_group_publishes_five_tools(group):
    names = {schema["name"] for schema in group._TOOL_SCHEMAS}
    assert names == {
        "link_type.list",
        "link_type.get",
        "link_type.create",
        "link_type.update",
        "link_type.reset",
    }


def test_every_published_tool_has_a_handler(group):
    assert set(group._TOOL_MAP) == {
        schema["name"] for schema in group._TOOL_SCHEMAS
    }
    for handler in group._TOOL_MAP.values():
        assert hasattr(group, handler)


def test_the_group_is_registered(db):
    from mcp_server.tool_registry import ToolRegistry

    registry = ToolRegistry()
    registry._ensure_groups()
    assert "link_type" in registry._groups


def test_create_link_no_longer_publishes_an_enum():
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    schema = next(
        s
        for s in CrossCuttingToolGroup()._TOOL_SCHEMAS
        if s["name"] == "traceability.create_link"
    )
    link_type = schema["inputSchema"]["properties"]["link_type"]
    assert link_type["type"] == "string"
    assert "enum" not in link_type


@pytest.mark.django_db
def test_list_returns_the_workspace_catalog(group, env):
    result = group._handle_list(
        params={"workspace_id": str(env["workspace"].id)},
        auth_context=env["ctx"],
        api_key="k",
    )
    assert result.success is True
    assert len(result.data["link_types"]) == 8


@pytest.mark.django_db
def test_every_payload_survives_stdlib_json_dumps(group, env):
    """The transport uses stdlib json.dumps — a UUID here is a 500."""
    result = group._handle_list(
        params={"workspace_id": str(env["workspace"].id)},
        auth_context=env["ctx"],
        api_key="k",
    )
    json.dumps(result.data)


@pytest.mark.django_db
def test_no_payload_uses_the_reserved_content_key(group, env):
    result = group._handle_list(
        params={"workspace_id": str(env["workspace"].id)},
        auth_context=env["ctx"],
        api_key="k",
    )
    assert "content" not in result.data


@pytest.mark.django_db
def test_get_returns_one_definition(group, env):
    result = group._handle_get(
        params={"workspace_id": str(env["workspace"].id), "key": "verifies"},
        auth_context=env["ctx"],
        api_key="k",
    )
    assert result.data["link_type"]["key"] == "verifies"


@pytest.mark.django_db
def test_get_of_an_unknown_key_is_a_not_found_error(group, env):
    result = group._handle_get(
        params={"workspace_id": str(env["workspace"].id), "key": "nope"},
        auth_context=env["ctx"],
        api_key="k",
    )
    assert result.success is False
    assert result.error_code == "NOT_FOUND"


@pytest.mark.django_db
def test_create_adds_a_tenant_type(group, env):
    definition = builtin_definition("mitigates")
    definition["built_in"] = False
    result = group._handle_create(
        params={"key": "conflicts-with", "definition": definition},
        auth_context=env["ctx"],
        api_key="k",
    )
    assert result.success is True
    assert result.data["link_type"]["key"] == "conflicts-with"


@pytest.mark.django_db
def test_create_with_a_bad_suspect_rule_is_a_validation_error(group, env):
    definition = builtin_definition("mitigates")
    definition["suspect_rule"] = "nope"
    result = group._handle_create(
        params={"key": "conflicts-with", "definition": definition},
        auth_context=env["ctx"],
        api_key="k",
    )
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "suspect_rule" in result.message


@pytest.mark.django_db
def test_update_then_reset_round_trips(group, env):
    definition = builtin_definition("mitigates")
    definition["impact_weight"] = 0.7
    updated = group._handle_update(
        params={
            "workspace_id": str(env["workspace"].id),
            "key": "mitigates",
            "definition": definition,
        },
        auth_context=env["ctx"],
        api_key="k",
    )
    assert updated.data["link_type"]["is_customized"] is True

    reset = group._handle_reset(
        params={"workspace_id": str(env["workspace"].id), "key": "mitigates"},
        auth_context=env["ctx"],
        api_key="k",
    )
    assert reset.data["link_type"]["is_customized"] is False


@pytest.mark.django_db
def test_list_requires_a_workspace_id(group, env):
    result = group._handle_list(params={}, auth_context=env["ctx"], api_key="k")
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def _provision_workspace_type(env, key: str, definition: dict) -> None:
    """Materialize a workspace row for a tenant-invented global type.

    ``link_type.create`` only writes the tenant-wide template
    (``GlobalLinkTypeDefinition``); the catalog the trace-link validator
    reads is the materialized per-workspace row
    (``link_types.catalog.resolve_catalog``) -- there is no
    auto-propagation to *existing* workspaces on create (only on update of
    an already-derived row), so provision it directly here, the same way
    ``provision_workspace_link_types`` seeds the built-ins.
    """
    from link_types.catalog import invalidate_workspace
    from link_types.models import GlobalLinkTypeDefinition, WorkspaceLinkTypeDefinition

    global_row = GlobalLinkTypeDefinition.objects.get(
        tenant_id=env["ctx"].tenant_id, key=key
    )
    WorkspaceLinkTypeDefinition.objects.create(
        workspace_id=env["workspace"].id,
        key=key,
        definition_json=definition,
        source_global=global_row,
        is_customized=False,
    )
    invalidate_workspace(str(env["workspace"].id))


@pytest.mark.django_db
def test_a_tenant_invented_link_type_passes_catalog_validation(group, env):
    """Regression for the removed MANUAL_LINK_TYPES pre-check (Task 21).

    The catalog (``link_types.catalog.validate_link_pair``) is the real,
    workspace-aware validation authority ``create_trace_link`` now relies
    on solely -- prove it actually accepts a tenant-invented, catalog
    -registered type instead of it being rejected up front by the removed,
    fixed, non-tenant-aware ``MANUAL_LINK_TYPES`` set.
    """
    from link_types.catalog import validate_link_pair

    definition = builtin_definition("mitigates")
    definition["built_in"] = False
    definition["allowed_pairs"] = [
        {"source_type": "Requirement", "target_type": "Requirement"}
    ]
    created = group._handle_create(
        params={"key": "conflicts-with", "definition": definition},
        auth_context=env["ctx"],
        api_key="k",
    )
    assert created.success is True
    _provision_workspace_type(env, "conflicts-with", definition)

    # Does not raise: the workspace catalog knows and accepts the type.
    validate_link_pair(
        env["workspace"].id,
        "conflicts-with",
        "Requirement",
        "Requirement",
        manual=True,
    )


@pytest.mark.django_db
def test_create_link_no_longer_rejects_via_the_removed_fixed_set(group, env):
    """The removed pre-check must not be reachable via any other path.

    A tenant-invented type is no longer rejected with the old, generic
    "Invalid link_type '...'. Valid types: [...]" message the deleted
    ``MANUAL_LINK_TYPES`` pre-check produced -- confirms the block is
    really gone, not just its import.

    KNOWN GAP (found by this test, not fixed by this task -- out of
    Task 21's file scope, see the task report): the request still ends in
    VALIDATION_ERROR today, one layer deeper than the catalog check this
    task wires up. ``traceability.trace_link_manager._validate_link_type``
    (Layer 1, unconditional, no ``manual`` distinction) enforces a
    *separate*, hardcoded ``LinkType`` enum that has no member for a
    tenant-invented key by design (see its docstring) -- so a genuinely
    novel key cannot be persisted end-to-end yet, even though the catalog
    itself already accepts it (see the sibling test above). Closing that
    gap needs a Layer-1 decision this task does not own.
    """
    from application.requirement_service import RequirementService
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup
    from workflow.services import create_default_workflow

    definition = builtin_definition("mitigates")
    definition["built_in"] = False
    definition["allowed_pairs"] = [
        {"source_type": "Requirement", "target_type": "Requirement"}
    ]
    created = group._handle_create(
        params={"key": "conflicts-with", "definition": definition},
        auth_context=env["ctx"],
        api_key="k",
    )
    assert created.success is True
    _provision_workspace_type(env, "conflicts-with", definition)

    create_default_workflow(
        workspace_id=env["workspace"].id,
        preset="standard",
        item_type="Requirement",
        tenant_id=env["ctx"].tenant_id,
    )
    requirement_service = RequirementService()
    source = requirement_service.create_requirement(
        workspace_id=env["workspace"].id, title="Source Req", ctx=env["ctx"]
    )
    target = requirement_service.create_requirement(
        workspace_id=env["workspace"].id, title="Target Req", ctx=env["ctx"]
    )

    result = CrossCuttingToolGroup().execute_tool(
        "traceability.create_link",
        params={
            "source_id": str(source.id),
            "target_id": str(target.id),
            "link_type": "conflicts-with",
        },
        auth_context=env["ctx"],
        api_key="k",
    )
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    # The removed pre-check's own wording -- pins that it is really gone.
    assert "Valid types:" not in (result.message or "")
