"""prompts/* capability (MCP-Modernisierung Task 7).

Unit tests for ``PromptsToolGroup`` (descriptor shape, workspace visibility,
message envelope, error mapping) plus wire tests through ``POST /mcp/`` with a
real API key and real ``PromptTemplate`` rows.
"""
import json
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tools.prompts import PromptsToolGroup


def _ctx():
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("viewer",),
        auth_method=AuthMethod.API_KEY,
    )


def _template(name, workspace_id=None):
    return SimpleNamespace(
        name=name, workspace_id=workspace_id, version=2, content="Body", is_active=True
    )


def test_group_is_invisible_in_tools_list():
    assert PromptsToolGroup().get_tool_schemas() == []


def test_list_returns_mcp_prompt_descriptors():
    with patch(
        "mcp_server.tools.prompts.list_active_templates",
        return_value=[_template("need_to_sysreq")],
    ), patch("mcp_server.tools.prompts.accessible_workspace_ids", return_value=[]):
        result = PromptsToolGroup().execute_tool(
            tool_name="prompt.list",
            params={},
            auth_context=_ctx(),
            api_key="reqlo_dummy",
        )
    assert result.success
    prompt = result.data["prompts"][0]
    assert prompt["name"] == "need_to_sysreq"
    assert prompt["arguments"] == []
    assert "version 2" in prompt["description"]


def test_list_hides_templates_of_inaccessible_workspaces():
    mine, theirs = uuid.uuid4(), uuid.uuid4()
    with patch(
        "mcp_server.tools.prompts.list_active_templates",
        return_value=[
            _template("global"),
            _template("mine", workspace_id=mine),
            _template("theirs", workspace_id=theirs),
        ],
    ), patch("mcp_server.tools.prompts.accessible_workspace_ids", return_value=[mine]):
        result = PromptsToolGroup().execute_tool(
            tool_name="prompt.list",
            params={},
            auth_context=_ctx(),
            api_key="reqlo_dummy",
        )
    assert {p["name"] for p in result.data["prompts"]} == {"global", "mine"}


def test_list_honours_explicit_workspace_id():
    workspace_id = uuid.uuid4()
    with patch(
        "mcp_server.tools.prompts.list_active_templates", return_value=[]
    ) as lister:
        PromptsToolGroup().execute_tool(
            tool_name="prompt.list",
            params={"workspace_id": str(workspace_id)},
            auth_context=_ctx(),
            api_key="reqlo_dummy",
        )
    assert lister.call_args.kwargs["workspace_id"] == workspace_id


def test_get_returns_a_single_user_message():
    with patch(
        "mcp_server.tools.prompts.try_resolve_template_content",
        return_value="Derive requirements from: {{need}}",
    ):
        result = PromptsToolGroup().execute_tool(
            tool_name="prompt.get",
            params={"name": "need_to_sysreq"},
            auth_context=_ctx(),
            api_key="reqlo_dummy",
        )
    assert result.success
    message = result.data["messages"][0]
    assert message["role"] == "user"
    assert message["content"]["type"] == "text"
    assert message["content"]["text"] == "Derive requirements from: {{need}}"


def test_get_unknown_name_is_not_found():
    with patch(
        "mcp_server.tools.prompts.try_resolve_template_content", return_value=None
    ):
        result = PromptsToolGroup().execute_tool(
            tool_name="prompt.get",
            params={"name": "nope"},
            auth_context=_ctx(),
            api_key="reqlo_dummy",
        )
    assert not result.success
    assert result.error_code == "NOT_FOUND"


def test_get_requires_a_name():
    result = PromptsToolGroup().execute_tool(
        tool_name="prompt.get",
        params={},
        auth_context=_ctx(),
        api_key="reqlo_dummy",
    )
    assert not result.success
    assert result.error_code == "VALIDATION_ERROR"


def test_protocol_handler_maps_prompt_methods():
    from mcp_server.protocol_handler import _METHOD_TO_INTERNAL_TOOL

    assert _METHOD_TO_INTERNAL_TOOL["prompts/list"] == "prompt.list"
    assert _METHOD_TO_INTERNAL_TOOL["prompts/get"] == "prompt.get"


def test_prompt_tools_are_read_only():
    from mcp_server.tool_registry import ToolRegistry

    registry = ToolRegistry()
    assert registry._is_write_tool("prompt.list") is False
    assert registry._is_write_tool("prompt.get") is False


def test_prompt_prefix_does_not_shadow_prompt_template_or_variable():
    """The router matches ``prefix + "."``; ``prompt.`` must not capture
    ``prompt_template.*`` / ``prompt_variable.*``."""
    from mcp_server.tool_registry import ToolRegistry

    registry = ToolRegistry()
    registry._ensure_groups()
    for name, group_name in (
        ("prompt.list", "PromptsToolGroup"),
        ("prompt.get", "PromptsToolGroup"),
        ("prompt_template.get", "PromptTemplateToolGroup"),
        ("prompt_template.list", "PromptTemplateToolGroup"),
        ("prompt_variable.list", "PromptVariableToolGroup"),
    ):
        group, error = registry._router.route(name)
        assert error is None, error
        assert type(group).__name__ == group_name, name


# ---------------------------------------------------------------------------
# Wire tests
# ---------------------------------------------------------------------------


def _rpc(client, method, params=None):
    return client.post(
        "/mcp/",
        data=json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
        ),
        content_type="application/json",
    )


@pytest.fixture
def seeded_templates(e2e_tenant, e2e_workspace):
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.models import PromptTemplate

    set_request_tenant(e2e_tenant.id)
    try:
        tenant_wide = PromptTemplate.objects.create(
            tenant=e2e_tenant,
            name="wire_tenant_prompt",
            content="Tenant-wide body: {{need}}",
            version=2,
            is_active=True,
            workspace_id=None,
        )
        workspace_scoped = PromptTemplate.objects.create(
            tenant=e2e_tenant,
            name="wire_workspace_prompt",
            content="Workspace body",
            version=1,
            is_active=True,
            workspace_id=e2e_workspace.id,
        )
    finally:
        clear_request_tenant()
    return tenant_wide, workspace_scoped


@pytest.mark.django_db
def test_wire_list_and_get(viewer_client, e2e_userrole_viewer, seeded_templates):
    listed = _rpc(viewer_client, "prompts/list").json()
    names = {prompt["name"] for prompt in listed["result"]["prompts"]}
    assert {"wire_tenant_prompt", "wire_workspace_prompt"} <= names

    got = _rpc(
        viewer_client, "prompts/get", {"name": "wire_tenant_prompt"}
    ).json()
    message = got["result"]["messages"][0]
    assert message["content"]["text"] == "Tenant-wide body: {{need}}"


@pytest.mark.django_db
def test_wire_get_unknown_prompt_is_not_found(viewer_client, e2e_userrole_viewer):
    body = _rpc(viewer_client, "prompts/get", {"name": "no_such_prompt"}).json()
    assert body["error"]["code"] == -32004  # NOT_FOUND


@pytest.mark.django_db
def test_wire_list_hides_foreign_workspace_templates(
    viewer_client, e2e_userrole_viewer, e2e_tenant
):
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.models import PromptTemplate, Workspace

    set_request_tenant(e2e_tenant.id)
    try:
        foreign = Workspace.objects.create(tenant=e2e_tenant, name="Prompt Foreign B")
        PromptTemplate.objects.create(
            tenant=e2e_tenant,
            name="foreign_workspace_prompt",
            content="secret",
            version=1,
            is_active=True,
            workspace_id=foreign.id,
        )
    finally:
        clear_request_tenant()

    listed = _rpc(viewer_client, "prompts/list").json()
    names = {prompt["name"] for prompt in listed["result"]["prompts"]}
    assert "foreign_workspace_prompt" not in names
