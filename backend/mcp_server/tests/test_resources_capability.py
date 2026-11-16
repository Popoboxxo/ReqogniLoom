"""resources/* capability (MCP-Modernisierung Task 6).

Two layers:
  * unit tests for the ``ResourcesToolGroup`` contract (URI scheme, envelopes,
    error mapping) with the renderer/service mocked;
  * wire tests through ``ProtocolHandler``/Django client for the real auth
    chain — ``resources/templates/list``, ``resources/list``, ``resources/read``
    plus the 403 (outside the caller's workspaces) and 404 (unknown artifact)
    paths.
"""
import json
import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from django.utils import timezone

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tools.base import ParameterError
from mcp_server.tools.resources import (
    ARTIFACT_URI_PREFIX,
    ResourcesToolGroup,
    parse_artifact_uri,
)


def _ctx():
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("viewer",),
        auth_method=AuthMethod.API_KEY,
    )


def _service_for(workspace_id):
    service = MagicMock()
    service.get_artifact_workspace_id.return_value = workspace_id
    return service


def test_uri_prefix():
    assert ARTIFACT_URI_PREFIX == "reqogniloom://artifact/"


def test_parse_valid_uri():
    artifact_id = uuid.uuid4()
    assert parse_artifact_uri(f"{ARTIFACT_URI_PREFIX}{artifact_id}") == artifact_id


@pytest.mark.parametrize(
    "bad", ["", "http://example.com/1", "reqogniloom://artifact/not-a-uuid"]
)
def test_parse_rejects_bad_uri(bad):
    with pytest.raises(ParameterError):
        parse_artifact_uri(bad)


def test_group_is_invisible_in_tools_list():
    assert ResourcesToolGroup().get_tool_schemas() == []


def test_read_returns_mcp_contents_envelope():
    artifact_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    with patch(
        "mcp_server.tools.resources.render_artifact_markdown",
        return_value="# Title\n",
    ), patch(
        "mcp_server.tools.prompts.accessible_workspace_ids",
        return_value=[workspace_id],
    ):
        result = ResourcesToolGroup(
            artifact_service=_service_for(workspace_id)
        ).execute_tool(
            tool_name="resource.read",
            params={"uri": f"{ARTIFACT_URI_PREFIX}{artifact_id}"},
            auth_context=_ctx(),
            api_key="reqlo_dummy",
        )
    assert result.success
    content = result.data["contents"][0]
    assert content["uri"] == f"{ARTIFACT_URI_PREFIX}{artifact_id}"
    assert content["mimeType"] == "text/markdown"
    assert content["text"] == "# Title\n"


def test_read_maps_not_found():
    from application.base import NotFoundError

    artifact_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    with patch(
        "mcp_server.tools.resources.render_artifact_markdown",
        side_effect=NotFoundError("nope"),
    ), patch(
        "mcp_server.tools.prompts.accessible_workspace_ids",
        return_value=[workspace_id],
    ):
        result = ResourcesToolGroup(
            artifact_service=_service_for(workspace_id)
        ).execute_tool(
            tool_name="resource.read",
            params={"uri": f"{ARTIFACT_URI_PREFIX}{artifact_id}"},
            auth_context=_ctx(),
            api_key="reqlo_dummy",
        )
    assert not result.success
    assert result.error_code == "NOT_FOUND"


def test_read_unknown_artifact_is_not_found_without_rendering():
    with patch(
        "mcp_server.tools.resources.render_artifact_markdown"
    ) as renderer:
        result = ResourcesToolGroup(
            artifact_service=_service_for(None)
        ).execute_tool(
            tool_name="resource.read",
            params={"uri": f"{ARTIFACT_URI_PREFIX}{uuid.uuid4()}"},
            auth_context=_ctx(),
            api_key="reqlo_dummy",
        )
    assert not result.success
    assert result.error_code == "NOT_FOUND"
    renderer.assert_not_called()


def test_read_outside_callers_workspaces_is_permission_denied():
    with patch(
        "mcp_server.tools.prompts.accessible_workspace_ids",
        return_value=[uuid.uuid4()],
    ), patch(
        "mcp_server.tools.resources.render_artifact_markdown"
    ) as renderer:
        result = ResourcesToolGroup(
            artifact_service=_service_for(uuid.uuid4())
        ).execute_tool(
            tool_name="resource.read",
            params={"uri": f"{ARTIFACT_URI_PREFIX}{uuid.uuid4()}"},
            auth_context=_ctx(),
            api_key="reqlo_dummy",
        )
    assert not result.success
    assert result.error_code == "PERMISSION_DENIED"
    renderer.assert_not_called()


def test_read_requires_a_uri():
    result = ResourcesToolGroup().execute_tool(
        tool_name="resource.read",
        params={},
        auth_context=_ctx(),
        api_key="reqlo_dummy",
    )
    assert not result.success
    assert result.error_code == "VALIDATION_ERROR"


def test_list_returns_resource_descriptors():
    artifact_id = uuid.uuid4()
    service = MagicMock()
    service.list_artifact_resources.return_value = [
        {
            "artifact_id": str(artifact_id),
            "artifact_type": "Requirement",
            "title": "Login must be possible",
        }
    ]
    result = ResourcesToolGroup(artifact_service=service).execute_tool(
        tool_name="resource.list",
        params={},
        auth_context=_ctx(),
        api_key="reqlo_dummy",
    )
    assert result.success
    resource = result.data["resources"][0]
    assert resource["uri"] == f"{ARTIFACT_URI_PREFIX}{artifact_id}"
    assert resource["name"] == "Login must be possible"
    assert resource["mimeType"] == "text/markdown"


def test_list_clamps_limit():
    service = MagicMock()
    service.list_artifact_resources.return_value = []
    ResourcesToolGroup(artifact_service=service).execute_tool(
        tool_name="resource.list",
        params={"limit": 99999},
        auth_context=_ctx(),
        api_key="reqlo_dummy",
    )
    assert service.list_artifact_resources.call_args.kwargs["limit"] == 200


def test_list_pages_with_next_cursor_when_full():
    service = MagicMock()
    service.list_artifact_resources.return_value = [
        {
            "artifact_id": str(uuid.uuid4()),
            "artifact_type": "Requirement",
            "title": "x",
        }
    ]
    result = ResourcesToolGroup(artifact_service=service).execute_tool(
        tool_name="resource.list",
        params={"limit": 1, "cursor": 10},
        auth_context=_ctx(),
        api_key="reqlo_dummy",
    )
    assert result.data["nextCursor"] == "11"


def test_templates_list_advertises_the_artifact_uri_template():
    result = ResourcesToolGroup().execute_tool(
        tool_name="resource.templates_list",
        params={},
        auth_context=_ctx(),
        api_key="reqlo_dummy",
    )
    assert result.success
    template = result.data["resourceTemplates"][0]
    assert template["uriTemplate"] == "reqogniloom://artifact/{id}"
    assert template["mimeType"] == "text/markdown"


def test_protocol_handler_maps_resource_methods():
    from mcp_server.protocol_handler import _METHOD_TO_INTERNAL_TOOL

    assert _METHOD_TO_INTERNAL_TOOL["resources/list"] == "resource.list"
    assert _METHOD_TO_INTERNAL_TOOL["resources/read"] == "resource.read"
    assert (
        _METHOD_TO_INTERNAL_TOOL["resources/templates/list"]
        == "resource.templates_list"
    )


def test_resource_tools_are_read_only():
    from mcp_server.tool_registry import ToolRegistry

    registry = ToolRegistry()
    for name in ("resource.list", "resource.read", "resource.templates_list"):
        assert registry._is_write_tool(name) is False


def test_resource_and_prompt_prefixes_add_no_public_tools():
    """Phase B must not grow ``tools/list`` (297 tools / 47 prefixes)."""
    from mcp_server.tool_registry import ToolRegistry

    names = {schema["name"] for schema in ToolRegistry().all_tool_schemas()}
    assert not any(name.startswith(("resource.", "prompt.")) for name in names)


def test_only_the_two_capability_groups_opt_out_of_schema_publication():
    """``capability_only`` is the documented exemption from the #1376 ratchet."""
    from mcp_server.tool_registry import ToolRegistry
    from mcp_server.tools.base import BaseToolGroup

    registry = ToolRegistry()
    registry._ensure_groups()
    flagged = {
        type(group).__name__
        for group in registry._router._groups.values()
        if isinstance(group, BaseToolGroup) and group.capability_only
    }
    assert flagged == {"ResourcesToolGroup", "PromptsToolGroup"}


# ---------------------------------------------------------------------------
# Wire tests — real auth/fence chain through POST /mcp/
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
def seeded_requirement(e2e_tenant, e2e_workspace):
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.models import Artifact, Requirement

    set_request_tenant(e2e_tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=e2e_tenant,
            workspace=e2e_workspace,
            artifact_type="Requirement",
        )
        return Requirement.objects.create(
            tenant=e2e_tenant,
            workspace=e2e_workspace,
            artifact=artifact,
            title="Wire resource requirement",
            description="Seeded for the resources/* wire tests.",
        )
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_wire_templates_list(viewer_client, e2e_userrole_viewer):
    response = _rpc(viewer_client, "resources/templates/list")
    body = response.json()
    assert response.status_code == 200
    assert body["result"]["resourceTemplates"][0]["uriTemplate"] == (
        "reqogniloom://artifact/{id}"
    )


@pytest.mark.django_db
def test_wire_list_and_read(viewer_client, e2e_userrole_viewer, seeded_requirement):
    listed = _rpc(viewer_client, "resources/list", {"limit": 10}).json()
    resources = listed["result"]["resources"]
    uris = {resource["uri"] for resource in resources}
    expected = f"{ARTIFACT_URI_PREFIX}{seeded_requirement.artifact_id}"
    assert expected in uris

    read = _rpc(viewer_client, "resources/read", {"uri": expected}).json()
    text = read["result"]["contents"][0]["text"]
    assert text.startswith("# Wire resource requirement")
    assert "- **Artifact Type:** Requirement" in text


@pytest.mark.django_db
def test_wire_read_unknown_artifact_is_not_found(
    viewer_client, e2e_userrole_viewer
):
    response = _rpc(
        viewer_client,
        "resources/read",
        {"uri": f"{ARTIFACT_URI_PREFIX}{uuid4()}"},
    )
    body = response.json()
    assert body["error"]["code"] == -32004  # NOT_FOUND
    assert "not found" in body["error"]["message"].lower()


@pytest.mark.django_db
def test_wire_read_foreign_workspace_is_permission_denied(
    viewer_client, e2e_userrole_viewer, e2e_tenant, seeded_requirement
):
    """A Viewer in workspace A must not read an artifact of workspace B."""
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.models import Artifact, Requirement, Workspace

    set_request_tenant(e2e_tenant.id)
    try:
        foreign = Workspace.objects.create(tenant=e2e_tenant, name="Foreign B")
        artifact = Artifact.objects.create(
            tenant=e2e_tenant, workspace=foreign, artifact_type="Requirement"
        )
        foreign_requirement = Requirement.objects.create(
            tenant=e2e_tenant,
            workspace=foreign,
            artifact=artifact,
            title="Secret of B",
        )
    finally:
        clear_request_tenant()

    response = _rpc(
        viewer_client,
        "resources/read",
        {"uri": f"{ARTIFACT_URI_PREFIX}{foreign_requirement.artifact_id}"},
    )
    body = response.json()
    assert body["error"]["code"] == -32001  # PERMISSION_DENIED


@pytest.mark.django_db
def test_wire_fenced_key_without_workspace_is_denied(
    e2e_tenant, e2e_workspace, e2e_user_member, e2e_userrole_member,
    seeded_requirement,
):
    from auth_tenancy.services.authentication import AuthenticationService

    key = (
        AuthenticationService()
        .create_api_key(
            user_id=e2e_user_member.id,
            tenant_id=e2e_tenant.id,
            name=f"res-fenced-{uuid4().hex[:8]}",
            principal_type="agent",
            agent_label="res-agent",
            scope="write",
            workspace_ids=[str(e2e_workspace.id)],
            expires_at=timezone.now() + timedelta(days=1),
        )
        .plaintext
    )
    from django.test import Client

    client = Client(HTTP_X_API_KEY=key)
    response = _rpc(
        client,
        "resources/read",
        {"uri": f"{ARTIFACT_URI_PREFIX}{seeded_requirement.artifact_id}"},
    )
    body = response.json()
    # Fail-closed: a workspace-less capability call carries no workspace the
    # fence could be checked against (#1444 precedent for list-only tools).
    assert body["error"]["code"] == -32001
