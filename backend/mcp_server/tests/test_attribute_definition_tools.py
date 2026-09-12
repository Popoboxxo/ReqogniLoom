"""attribute_definition.* MCP tools (spec section 5)."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from mcp_server.tools.attribute_definition import AttributeDefinitionToolGroup

VALID_API_KEY = "reqlo_test_key"

PAYLOAD = {
    "item_type": "Risk", "preset": "standard", "is_customized": False,
    "version": 1, "attributes": [{"name": "title", "kind": "core", "type": "text"}],
}


@pytest.fixture
def group() -> AttributeDefinitionToolGroup:
    return AttributeDefinitionToolGroup()


@pytest.fixture
def ctx() -> MagicMock:
    context = MagicMock()
    context.tenant_id = uuid.uuid4()
    return context


def test_tool_map_exposes_exactly_thirteen_tools(group) -> None:
    assert set(group._TOOL_MAP) == {
        "attribute_definition.list",
        "attribute_definition.get",
        "attribute_definition.update",
        "attribute_definition.reset",
        "attribute_definition.create",
        "attribute_definition.delete",
        "attribute_definition.create_workspace",
        "attribute_definition.delete_workspace",
        "attribute_definition.count_usages",
        "attribute_definition.export",
        "attribute_definition.export_workspace",
        "attribute_definition.import",
        "attribute_definition.import_workspace",
    }


def test_get_declares_workspace_id_as_required(group) -> None:
    """P4: a *declared* workspace_id is not scoping — it must be required."""
    schema = {t["name"]: t["inputSchema"] for t in group.get_tool_schemas()}
    assert "workspace_id" in schema["attribute_definition.get"]["required"]
    assert "workspace_id" in schema["attribute_definition.update"]["required"]
    assert "workspace_id" in schema["attribute_definition.reset"]["required"]


@pytest.mark.django_db
def test_get_returns_the_resolved_definition(group, ctx) -> None:
    with patch(
        "mcp_server.tools.attribute_definition.AttributeDefinitionService"
    ) as service:
        service.return_value.resolve.return_value = PAYLOAD
        result = group.execute_tool(
            tool_name="attribute_definition.get",
            params={"item_type": "Risk", "workspace_id": str(uuid.uuid4())},
            auth_context=ctx,
            api_key=VALID_API_KEY,
        )
    assert result.success is True
    assert result.data["definition"]["item_type"] == "Risk"


@pytest.mark.django_db
def test_get_without_workspace_id_is_a_validation_error(group, ctx) -> None:
    result = group.execute_tool(
        tool_name="attribute_definition.get",
        params={"item_type": "Risk"},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_list_returns_the_global_defaults(group, ctx) -> None:
    with patch(
        "mcp_server.tools.attribute_definition.AttributeDefinitionService"
    ) as service:
        service.return_value.list_global.return_value = [PAYLOAD]
        result = group.execute_tool(
            tool_name="attribute_definition.list",
            params={"item_type": "Risk"},
            auth_context=ctx,
            api_key=VALID_API_KEY,
        )
    assert result.success is True
    assert result.data["count"] == 1
    assert result.data["definitions"][0]["item_type"] == "Risk"


@pytest.mark.django_db
def test_list_maps_permission_denied(group, ctx) -> None:
    from application.base import PermissionDeniedError

    with patch(
        "mcp_server.tools.attribute_definition.AttributeDefinitionService"
    ) as service:
        service.return_value.list_global.side_effect = PermissionDeniedError("nope")
        result = group.execute_tool(
            tool_name="attribute_definition.list",
            params={},
            auth_context=ctx,
            api_key=VALID_API_KEY,
        )
    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


@pytest.mark.django_db
def test_update_rejects_a_non_list_attributes_param(group, ctx) -> None:
    result = group.execute_tool(
        tool_name="attribute_definition.update",
        params={"item_type": "Risk", "workspace_id": str(uuid.uuid4()), "attributes": {}},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_update_maps_a_schema_error_to_validation_error(group, ctx) -> None:
    from application.attribute_definition_service import AttributeSchemaError

    with patch(
        "mcp_server.tools.attribute_definition.AttributeDefinitionService"
    ) as service:
        service.return_value.update_workspace.side_effect = AttributeSchemaError(
            ["title: a core attribute may not change its 'type'"]
        )
        result = group.execute_tool(
            tool_name="attribute_definition.update",
            params={"item_type": "Risk", "workspace_id": str(uuid.uuid4()), "attributes": []},
            auth_context=ctx,
            api_key=VALID_API_KEY,
        )
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_update_maps_not_found(group, ctx) -> None:
    from application.attribute_definition_service import AttributeDefinitionNotFound

    with patch(
        "mcp_server.tools.attribute_definition.AttributeDefinitionService"
    ) as service:
        service.return_value.update_workspace.side_effect = AttributeDefinitionNotFound(
            "no such definition"
        )
        result = group.execute_tool(
            tool_name="attribute_definition.update",
            params={"item_type": "Risk", "workspace_id": str(uuid.uuid4()), "attributes": []},
            auth_context=ctx,
            api_key=VALID_API_KEY,
        )
    assert result.success is False
    assert result.error_code == "NOT_FOUND"


@pytest.mark.django_db
def test_reset_returns_the_restored_definition(group, ctx) -> None:
    with patch(
        "mcp_server.tools.attribute_definition.AttributeDefinitionService"
    ) as service:
        service.return_value.reset_workspace.return_value = PAYLOAD
        result = group.execute_tool(
            tool_name="attribute_definition.reset",
            params={"item_type": "Risk", "workspace_id": str(uuid.uuid4())},
            auth_context=ctx,
            api_key=VALID_API_KEY,
        )
    assert result.success is True
    assert result.data["definition"]["item_type"] == "Risk"


def _risk_workspace_with_definition():
    """A real tenant/workspace plus a bootstrapped ``Risk`` global default.

    ``sections`` persistence has to be proven against the real store, not a
    mocked service — a forwarded-but-dropped parameter would pass a mock test.
    """
    from attribute_definitions.global_definition_store import (
        GlobalAttributeDefinitionStore,
    )
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.models import Tenant, Workspace

    tenant = Tenant.objects.create(
        name="AttrDef Sections",
        slug=f"attrdef-sections-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="ws-sections", preset={"name": "standard"}
        )
    finally:
        clear_request_tenant()

    GlobalAttributeDefinitionStore().initialize(
        tenant.id,
        "Risk",
        "standard",
        [{"name": "title", "kind": "core", "type": "text"}],
    )
    return tenant, workspace


def _admin_ctx(tenant):
    from auth_tenancy.context import AuthContext, AuthMethod

    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.API_KEY,
    )


def test_update_schema_declares_sections(group) -> None:
    schema = {t["name"]: t["inputSchema"] for t in group.get_tool_schemas()}
    assert "sections" in schema["attribute_definition.update"]["properties"]
    assert "sections" not in schema["attribute_definition.update"]["required"]


@pytest.mark.django_db
def test_update_persists_a_given_sections_list(group) -> None:
    """Epic #934 / WS1 #935: the MCP twin must accept ``sections`` exactly
    like the REST PUT does, instead of silently dropping it."""
    from application.attribute_definition_service import AttributeDefinitionService

    tenant, workspace = _risk_workspace_with_definition()
    admin_ctx = _admin_ctx(tenant)
    definition = AttributeDefinitionService().resolve(admin_ctx, "Risk", workspace.id)
    sections = [
        {"name": "general", "order": 0, "visible": False, "layout": "full"},
        {"name": "more", "order": 1, "visible": True, "layout": "half"},
    ]

    result = group.execute_tool(
        tool_name="attribute_definition.update",
        params={
            "item_type": "Risk",
            "workspace_id": str(workspace.id),
            "attributes": definition["attributes"],
            "sections": sections,
        },
        auth_context=admin_ctx,
        api_key=VALID_API_KEY,
    )

    assert result.success is True, result.message
    from attribute_definitions.schema import stored_sections
    from attribute_definitions.workspace_definition_store import (
        WorkspaceAttributeDefinitionStore,
    )

    row = WorkspaceAttributeDefinitionStore().get(tenant.id, workspace.id, "Risk")
    assert row is not None
    assert stored_sections(row.definition_json) == sections


@pytest.mark.django_db
def test_update_rejects_an_invalid_sections_payload(group) -> None:
    """An invalid ``sections`` payload must surface as a VALIDATION_ERROR,
    not be silently dropped as it was before this increment."""
    from application.attribute_definition_service import AttributeDefinitionService

    tenant, workspace = _risk_workspace_with_definition()
    admin_ctx = _admin_ctx(tenant)
    definition = AttributeDefinitionService().resolve(admin_ctx, "Risk", workspace.id)

    result = group.execute_tool(
        tool_name="attribute_definition.update",
        params={
            "item_type": "Risk",
            "workspace_id": str(workspace.id),
            "attributes": definition["attributes"],
            "sections": [{"name": "general", "order": 0, "layout": "no-such-layout"}],
        },
        auth_context=admin_ctx,
        api_key=VALID_API_KEY,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "layout" in result.message


@pytest.mark.django_db
def test_update_rejects_a_non_list_sections_param(group, ctx) -> None:
    result = group.execute_tool(
        tool_name="attribute_definition.update",
        params={
            "item_type": "Risk",
            "workspace_id": str(uuid.uuid4()),
            "attributes": [],
            "sections": "nope",
        },
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_get_maps_a_cross_tenant_workspace_id_to_permission_denied() -> None:
    """Adversarial probe (standing instruction on this SDD run): a
    ``workspace_id`` the caller's tenant does not own must be a caller-facing
    PERMISSION_DENIED — the same mapping
    ``WorkspaceAttributeDefinitionView.get`` uses for the identical
    ``CrossTenantWorkspaceError`` raised by
    ``AttributeDefinitionService.resolve()`` -- NOT an uncaught 500-class
    INTERNAL_ERROR (which is what the base ``BaseToolGroup.execute_tool``
    dispatcher's blanket ``except Exception`` would otherwise turn it into).
    Uses two *real* tenants and a real DB row on purpose — a mocked service
    would hide exactly this exception-mapping gap.
    """
    from attribute_definitions.global_definition_store import (
        GlobalAttributeDefinitionStore,
    )
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.models import Tenant, Workspace

    tenant_a = Tenant.objects.create(
        name="Tenant A", slug=f"tenant-a-{uuid.uuid4().hex[:8]}", is_active=True
    )
    tenant_b = Tenant.objects.create(
        name="Tenant B", slug=f"tenant-b-{uuid.uuid4().hex[:8]}", is_active=True
    )

    set_request_tenant(tenant_b.id)
    try:
        workspace_b = Workspace.objects.create(
            tenant=tenant_b, name="ws-b", preset={"name": "standard"}
        )
    finally:
        clear_request_tenant()

    GlobalAttributeDefinitionStore().initialize(
        tenant_b.id, "Risk", "standard", [{"name": "title", "kind": "core", "type": "text"}]
    )

    caller_ctx = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        active_roles=("Viewer",),
        auth_method=AuthMethod.API_KEY,
    )

    group = AttributeDefinitionToolGroup()
    result = group.execute_tool(
        tool_name="attribute_definition.get",
        params={"item_type": "Risk", "workspace_id": str(workspace_b.id)},
        auth_context=caller_ctx,
        api_key=VALID_API_KEY,
    )
    assert result.success is False, (
        f"expected a rejection, got a 200-class result: {result.data!r}"
    )
    assert result.error_code == "PERMISSION_DENIED", (
        f"cross-tenant workspace_id must map to PERMISSION_DENIED (matching "
        f"the REST view's CrossTenantWorkspaceError -> 403 mapping), got "
        f"{result.error_code!r} instead"
    )


def test_create_workspace_declares_workspace_id_as_required(group) -> None:
    schema = {t["name"]: t["inputSchema"] for t in group.get_tool_schemas()}
    assert "workspace_id" in schema["attribute_definition.create_workspace"]["required"]
    assert "workspace_id" in schema["attribute_definition.delete_workspace"]["required"]


@pytest.mark.django_db
def test_create_returns_the_updated_global_definition(group, ctx) -> None:
    with patch(
        "mcp_server.tools.attribute_definition.AttributeDefinitionService"
    ) as service:
        service.return_value.create_global.return_value = PAYLOAD
        result = group.execute_tool(
            tool_name="attribute_definition.create",
            params={
                "item_type": "Risk", "preset": "standard",
                "attribute": {"name": "note", "kind": "extended", "type": "text"},
            },
            auth_context=ctx,
            api_key=VALID_API_KEY,
        )
    assert result.success is True
    assert result.data["definition"]["item_type"] == "Risk"


@pytest.mark.django_db
def test_create_rejects_a_non_object_attribute_param(group, ctx) -> None:
    result = group.execute_tool(
        tool_name="attribute_definition.create",
        params={"item_type": "Risk", "preset": "standard", "attribute": "oops"},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_create_maps_a_schema_error_to_validation_error(group, ctx) -> None:
    from application.attribute_definition_service import AttributeSchemaError

    with patch(
        "mcp_server.tools.attribute_definition.AttributeDefinitionService"
    ) as service:
        service.return_value.create_global.side_effect = AttributeSchemaError(
            ["'title' already exists"]
        )
        result = group.execute_tool(
            tool_name="attribute_definition.create",
            params={
                "item_type": "Risk", "preset": "standard",
                "attribute": {"name": "title", "kind": "extended", "type": "text"},
            },
            auth_context=ctx,
            api_key=VALID_API_KEY,
        )
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_delete_returns_the_updated_global_definition(group, ctx) -> None:
    with patch(
        "mcp_server.tools.attribute_definition.AttributeDefinitionService"
    ) as service:
        service.return_value.delete_global.return_value = PAYLOAD
        result = group.execute_tool(
            tool_name="attribute_definition.delete",
            params={"item_type": "Risk", "preset": "standard", "name": "note"},
            auth_context=ctx,
            api_key=VALID_API_KEY,
        )
    assert result.success is True
    assert result.data["definition"]["item_type"] == "Risk"


@pytest.mark.django_db
def test_create_workspace_returns_the_updated_definition(group, ctx) -> None:
    with patch(
        "mcp_server.tools.attribute_definition.AttributeDefinitionService"
    ) as service:
        service.return_value.create_workspace.return_value = PAYLOAD
        result = group.execute_tool(
            tool_name="attribute_definition.create_workspace",
            params={
                "item_type": "Risk", "workspace_id": str(uuid.uuid4()),
                "attribute": {"name": "note", "kind": "extended", "type": "text"},
            },
            auth_context=ctx,
            api_key=VALID_API_KEY,
        )
    assert result.success is True
    assert result.data["definition"]["item_type"] == "Risk"


@pytest.mark.django_db
def test_create_workspace_maps_cross_tenant_to_permission_denied(group, ctx) -> None:
    from presets.exceptions import CrossTenantWorkspaceError

    with patch(
        "mcp_server.tools.attribute_definition.AttributeDefinitionService"
    ) as service:
        service.return_value.create_workspace.side_effect = CrossTenantWorkspaceError(
            "not your workspace"
        )
        result = group.execute_tool(
            tool_name="attribute_definition.create_workspace",
            params={
                "item_type": "Risk", "workspace_id": str(uuid.uuid4()),
                "attribute": {"name": "note", "kind": "extended", "type": "text"},
            },
            auth_context=ctx,
            api_key=VALID_API_KEY,
        )
    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


@pytest.mark.django_db
def test_delete_workspace_returns_the_updated_definition(group, ctx) -> None:
    with patch(
        "mcp_server.tools.attribute_definition.AttributeDefinitionService"
    ) as service:
        service.return_value.delete_workspace.return_value = PAYLOAD
        result = group.execute_tool(
            tool_name="attribute_definition.delete_workspace",
            params={"item_type": "Risk", "workspace_id": str(uuid.uuid4()), "name": "note"},
            auth_context=ctx,
            api_key=VALID_API_KEY,
        )
    assert result.success is True
    assert result.data["definition"]["item_type"] == "Risk"


@pytest.mark.django_db
def test_delete_workspace_maps_cross_tenant_to_permission_denied(group, ctx) -> None:
    from presets.exceptions import CrossTenantWorkspaceError

    with patch(
        "mcp_server.tools.attribute_definition.AttributeDefinitionService"
    ) as service:
        service.return_value.delete_workspace.side_effect = CrossTenantWorkspaceError(
            "not your workspace"
        )
        result = group.execute_tool(
            tool_name="attribute_definition.delete_workspace",
            params={"item_type": "Risk", "workspace_id": str(uuid.uuid4()), "name": "note"},
            auth_context=ctx,
            api_key=VALID_API_KEY,
        )
    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


@pytest.mark.django_db
def test_count_usages_returns_the_count(group, ctx) -> None:
    with patch(
        "mcp_server.tools.attribute_definition.AttributeDefinitionService"
    ) as service:
        service.return_value.count_usages.return_value = 3
        result = group.execute_tool(
            tool_name="attribute_definition.count_usages",
            params={"item_type": "Risk", "workspace_id": str(uuid.uuid4()), "name": "note"},
            auth_context=ctx,
            api_key=VALID_API_KEY,
        )
    assert result.success is True
    assert result.data["count"] == 3


@pytest.mark.django_db
def test_count_usages_maps_permission_denied(group, ctx) -> None:
    from application.base import PermissionDeniedError

    with patch(
        "mcp_server.tools.attribute_definition.AttributeDefinitionService"
    ) as service:
        service.return_value.count_usages.side_effect = PermissionDeniedError("nope")
        result = group.execute_tool(
            tool_name="attribute_definition.count_usages",
            params={"item_type": "Risk", "workspace_id": str(uuid.uuid4()), "name": "note"},
            auth_context=ctx,
            api_key=VALID_API_KEY,
        )
    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


@pytest.mark.django_db
def test_export_returns_the_document(group, ctx) -> None:
    document = {"schema_version": 1, "item_type": "Risk", "attributes": [], "sections": []}
    with patch(
        "mcp_server.tools.attribute_definition.AttributeDefinitionService"
    ) as service:
        service.return_value.export_definition.return_value = document
        result = group.execute_tool(
            tool_name="attribute_definition.export",
            params={"item_type": "Risk", "preset": "standard"},
            auth_context=ctx,
            api_key=VALID_API_KEY,
        )
    assert result.success is True
    assert result.data["document"] == document


@pytest.mark.django_db
def test_export_workspace_maps_cross_tenant_to_permission_denied(group, ctx) -> None:
    from presets.exceptions import CrossTenantWorkspaceError

    with patch(
        "mcp_server.tools.attribute_definition.AttributeDefinitionService"
    ) as service:
        service.return_value.export_definition.side_effect = CrossTenantWorkspaceError("nope")
        result = group.execute_tool(
            tool_name="attribute_definition.export_workspace",
            params={"item_type": "Risk", "workspace_id": str(uuid.uuid4())},
            auth_context=ctx,
            api_key=VALID_API_KEY,
        )
    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


@pytest.mark.django_db
def test_import_rejects_a_non_object_document(group, ctx) -> None:
    result = group.execute_tool(
        tool_name="attribute_definition.import",
        params={"item_type": "Risk", "preset": "standard", "document": "nope"},
        auth_context=ctx,
        api_key=VALID_API_KEY,
    )
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_import_returns_the_updated_definition(group, ctx) -> None:
    with patch(
        "mcp_server.tools.attribute_definition.AttributeDefinitionService"
    ) as service:
        service.return_value.import_definition.return_value = PAYLOAD
        result = group.execute_tool(
            tool_name="attribute_definition.import",
            params={
                "item_type": "Risk", "preset": "standard",
                "document": {"schema_version": 1, "attributes": []},
            },
            auth_context=ctx,
            api_key=VALID_API_KEY,
        )
    assert result.success is True
    assert result.data["definition"]["item_type"] == "Risk"


@pytest.mark.django_db
def test_import_workspace_maps_a_schema_error_to_validation_error(group, ctx) -> None:
    from application.attribute_definition_service import AttributeSchemaError

    with patch(
        "mcp_server.tools.attribute_definition.AttributeDefinitionService"
    ) as service:
        service.return_value.import_definition.side_effect = AttributeSchemaError(
            ["unrecognized schema_version"]
        )
        result = group.execute_tool(
            tool_name="attribute_definition.import_workspace",
            params={
                "item_type": "Risk", "workspace_id": str(uuid.uuid4()),
                "document": {"schema_version": 99, "attributes": []},
            },
            auth_context=ctx,
            api_key=VALID_API_KEY,
        )
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_payload_is_json_serialisable_with_the_stdlib_encoder() -> None:
    """The MCP transport uses stdlib json.dumps — a UUID in a payload 500s."""
    import json

    from mcp_server.tools.attribute_definition import _definition_payload

    json.dumps(_definition_payload(PAYLOAD))
