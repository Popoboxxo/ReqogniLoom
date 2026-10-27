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
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import (
    TREE_DISPLAY_SCOPE_WORKSPACE,
    TreeDisplayConfig,
)
from auth_tenancy.services.authentication import AuthenticationService
from mcp_server.tool_registry import ToolRegistry
from persistence.models import Tenant


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


# ---------------------------------------------------------------------------
# Capability tier (R6, ENT-C3 = B): workspace/global are governance acts
# ---------------------------------------------------------------------------


def _dispatch(tool_name: str, params: dict, api_key: str):
    return ToolRegistry().dispatch_request(
        tool_name=tool_name, params=params, api_key=api_key
    )


def _make_key(tenant: Tenant, user_id, scope: str) -> str:
    return (
        AuthenticationService()
        .create_api_key(
            user_id=user_id,
            tenant_id=tenant.id,
            name=f"form-{scope}-{uuid.uuid4().hex[:8]}",
            scope=scope,
            expires_at=timezone.now() + timedelta(days=1),
        )
        .plaintext
    )


@pytest.fixture
def author_key_admin(e2e_tenant: Tenant, e2e_user_admin) -> str:
    return _make_key(e2e_tenant, e2e_user_admin.id, "author")


@pytest.fixture
def admin_key_admin(e2e_tenant: Tenant, e2e_user_admin) -> str:
    return _make_key(e2e_tenant, e2e_user_admin.id, "admin")


@pytest.mark.django_db
def test_author_key_of_an_admin_owner_may_not_set_a_workspace_default(
    author_key_admin: str, e2e_workspace, e2e_userrole_admin
) -> None:
    """R6: the ADMIN tier sits above the role matrix."""
    result = _dispatch(
        "create_form_definition.set",
        {
            "scope": "workspace",
            "item_type": "Requirement",
            "fields": None,
            "workspace_id": str(e2e_workspace.id),
        },
        author_key_admin,
    )

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    assert (
        TreeDisplayConfig.unscoped.filter(
            scope=TREE_DISPLAY_SCOPE_WORKSPACE, workspace_id=e2e_workspace.id
        ).count()
        == 0
    )


@pytest.mark.django_db
def test_author_key_may_not_import_a_global_default(
    author_key_admin: str, e2e_workspace, e2e_userrole_admin
) -> None:
    """``import`` is a second write path into the same levels — gated alike."""
    result = _dispatch(
        "create_form_definition.import",
        {
            "scope": "global",
            "item_type": "Requirement",
            "document": {"schema_version": 1, "fields": None},
        },
        author_key_admin,
    )

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    assert not TreeDisplayConfig.unscoped.filter(scope="global").exists()


@pytest.mark.django_db
def test_author_key_may_still_set_its_own_level(
    author_key_admin: str, e2e_workspace, e2e_userrole_admin
) -> None:
    """The gate is per scope — self-service must stay reachable."""
    result = _dispatch(
        "create_form_definition.set",
        {"scope": "user", "item_type": "Requirement", "fields": None},
        author_key_admin,
    )

    assert result.success is True, result
    assert result.data["scope"] == "user"


@pytest.mark.django_db
def test_admin_key_may_set_the_workspace_default(
    admin_key_admin: str, e2e_workspace, e2e_userrole_admin
) -> None:
    result = _dispatch(
        "create_form_definition.set",
        {
            "scope": "workspace",
            "item_type": "Requirement",
            "fields": None,
            "workspace_id": str(e2e_workspace.id),
        },
        admin_key_admin,
    )

    assert result.success is True, result
    assert TreeDisplayConfig.unscoped.filter(
        scope=TREE_DISPLAY_SCOPE_WORKSPACE, workspace_id=e2e_workspace.id
    ).exists()
