"""MCP ``tree_display_config.*`` tool group — configurable navigation tree (#1257).

The two handlers are thin wrappers over ``TreeDisplayConfigService``; these tests
pin the published schemas, the argument normalisation, the delegation contract
and the two classification gates the rest of the MCP suite depends on (the
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
    from mcp_server.tools.tree_display_config import TreeDisplayConfigToolGroup

    return TreeDisplayConfigToolGroup()


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
        f"application.tree_display_config_service.TreeDisplayConfigService.{method}",
        return_value={"scope": "user", "item_type": "Requirement", "fields": []},
    )


# ---------------------------------------------------------------------------
# Published surface
# ---------------------------------------------------------------------------


def test_group_publishes_exactly_two_tools(group) -> None:
    names = {schema["name"] for schema in group._TOOL_SCHEMAS}
    assert names == {"tree_display_config.get", "tree_display_config.set"}
    assert set(group._TOOL_MAP) == names
    for handler in group._TOOL_MAP.values():
        assert hasattr(group, handler)


def test_get_schema_offers_the_effective_and_per_level_scopes(group) -> None:
    schema = next(
        s for s in group._TOOL_SCHEMAS if s["name"] == "tree_display_config.get"
    )
    enum = schema["inputSchema"]["properties"]["scope"]["enum"]
    assert enum == ["effective", "user", "workspace", "global", "default"]
    # Nothing is required: the default scope is "effective" and item_type is
    # only needed there (a per-level read may ask for the whole map).
    assert "required" not in schema["inputSchema"]


def test_set_schema_requires_scope_item_type_and_fields(group) -> None:
    schema = next(
        s for s in group._TOOL_SCHEMAS if s["name"] == "tree_display_config.set"
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
    assert "tree_display_config" in registry._groups
    # Read-exempt: ``.get`` does not end on ".read"/".query", so it is listed
    # explicitly in _READ_ONLY_TOOL_NAMES. ``.set`` stays fail-closed write.
    assert registry._is_write_tool("tree_display_config.get") is False
    assert registry._is_write_tool("tree_display_config.set") is True


def test_get_is_classified_for_workspace_scope_coverage() -> None:
    """The coverage ratchet in test_mcp_workspace_scope.py needs this entry."""
    from mcp_server.workspace_scope import TENANT_SCOPED_READ_TOOLS

    assert "tree_display_config.get" in TENANT_SCOPED_READ_TOOLS


def test_set_stays_author_tier_because_the_user_level_is_self_service() -> None:
    """The name-based tier map cannot express a per-parameter rule.

    ``tree_display_config.set`` also writes the caller's *own* level, so a
    blanket ADMIN tier (the ``preference.set_default`` route) would take
    self-service away from every AUTHOR key. The registry keeps the tool at
    WRITE tier; the workspace/global governance gate is evaluated per request
    in the handler (``scope in {"workspace","global"}`` →
    ``Operation.WORKSPACE_CONFIG``). See the tier tests below.
    """
    from auth_tenancy.services.authorization import Operation
    from mcp_server.tool_registry import ToolRegistry

    assert (
        ToolRegistry()._required_scope_operation("tree_display_config.set")
        is Operation.WRITE
    )


# ---------------------------------------------------------------------------
# tree_display_config.get
# ---------------------------------------------------------------------------


def test_get_effective_requires_an_item_type(group, ctx) -> None:
    result = _call(group, "tree_display_config.get", {}, ctx)

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_get_rejects_an_unknown_scope(group, ctx) -> None:
    result = _call(
        group, "tree_display_config.get", {"scope": "everything"}, ctx
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_get_effective_delegates_to_get_config(group, ctx) -> None:
    workspace_id = str(uuid.uuid4())
    payload = {"scope": "default", "item_type": "Requirement", "fields": []}
    with patch(
        "application.tree_display_config_service.TreeDisplayConfigService.get_config",
        return_value=payload,
    ) as handler:
        result = _call(
            group,
            "tree_display_config.get",
            {"scope": "effective", "item_type": "Requirement", "workspace_id": workspace_id},
            ctx,
        )

    assert result.success is True
    assert result.data == payload
    assert handler.call_args.kwargs["item_type"] == "Requirement"
    assert str(handler.call_args.kwargs["workspace_id"]) == workspace_id


def test_get_defaults_to_the_effective_scope(group, ctx) -> None:
    with patch(
        "application.tree_display_config_service.TreeDisplayConfigService.get_config",
        return_value={},
    ) as handler:
        _call(
            group,
            "tree_display_config.get",
            {"item_type": "Requirement"},
            ctx,
        )

    assert handler.called


def test_get_per_level_delegates_to_get_scope(group, ctx) -> None:
    with patch(
        "application.tree_display_config_service.TreeDisplayConfigService.get_scope",
        return_value={"scope": "global", "config": {}},
    ) as handler:
        result = _call(
            group, "tree_display_config.get", {"scope": "global"}, ctx
        )

    assert result.success is True
    assert handler.call_args.kwargs["scope"] == "global"
    assert handler.call_args.kwargs["item_type"] is None


def test_get_rejects_a_malformed_workspace_id(group, ctx) -> None:
    result = _call(
        group,
        "tree_display_config.get",
        {"scope": "workspace", "workspace_id": "not-a-uuid"},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# tree_display_config.set
# ---------------------------------------------------------------------------


def test_set_requires_an_item_type(group, ctx) -> None:
    result = _call(
        group, "tree_display_config.set", {"scope": "user", "fields": []}, ctx
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_set_requires_a_workspace_id_for_the_workspace_scope(group, ctx) -> None:
    result = _call(
        group,
        "tree_display_config.set",
        {"scope": "workspace", "item_type": "Requirement", "fields": ["uid"]},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_set_rejects_a_workspace_id_on_the_user_scope(group, ctx) -> None:
    """Scope 'user' is self-service; a workspace there would be ignored."""
    result = _call(
        group,
        "tree_display_config.set",
        {
            "scope": "user",
            "item_type": "Requirement",
            "fields": ["uid"],
            "workspace_id": str(uuid.uuid4()),
        },
        ctx,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_set_rejects_a_non_list_fields_payload(group, ctx) -> None:
    result = _call(
        group,
        "tree_display_config.set",
        {"scope": "user", "item_type": "Requirement", "fields": "uid"},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_set_forwards_the_ordered_field_list(group, ctx) -> None:
    with _service_patch("set_config") as handler:
        result = _call(
            group,
            "tree_display_config.set",
            {
                "scope": "user",
                "item_type": "Requirement",
                "fields": ["status", {"key": "uid", "width": "half"}],
            },
            ctx,
        )

    assert result.success is True
    kwargs = handler.call_args.kwargs
    assert kwargs["scope"] == "user"
    assert kwargs["item_type"] == "Requirement"
    assert kwargs["fields"] == ["status", {"key": "uid", "width": "half"}]
    assert kwargs["workspace_id"] is None


def test_set_null_resets_the_level(group, ctx) -> None:
    with _service_patch("set_config") as handler:
        result = _call(
            group,
            "tree_display_config.set",
            {"scope": "global", "item_type": "Requirement", "fields": None},
            ctx,
        )

    assert result.success is True
    assert handler.call_args.kwargs["fields"] is None


def test_set_maps_a_permission_error_to_permission_denied(group, ctx) -> None:
    from persistence.errors import PermissionDeniedError

    with patch(
        "application.tree_display_config_service.TreeDisplayConfigService.set_config",
        side_effect=PermissionDeniedError("nope"),
    ):
        result = _call(
            group,
            "tree_display_config.set",
            {"scope": "global", "item_type": "Requirement", "fields": ["uid"]},
            ctx,
        )

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


def test_unknown_tool_is_reported(group, ctx) -> None:
    result = _call(group, "tree_display_config.nope", {}, ctx)

    assert result.success is False
    assert result.error_code == "UNKNOWN_TOOL"


# ---------------------------------------------------------------------------
# Capability tier (R6, ENT-C3 = B): workspace/global are governance acts
# ---------------------------------------------------------------------------


def _dispatch(tool_name: str, params: dict, api_key: str):
    return ToolRegistry().dispatch_request(
        tool_name=tool_name, params=params, api_key=api_key
    )


def _make_key(tenant: Tenant, user_id, scope: str) -> str:
    """Issue an API key of *scope* for an already-privileged owner.

    The tier is a property of the key, not of the owner — this is what makes
    the "privileged owner, narrow key" case testable end to end.
    """
    return (
        AuthenticationService()
        .create_api_key(
            user_id=user_id,
            tenant_id=tenant.id,
            name=f"tree-{scope}-{uuid.uuid4().hex[:8]}",
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
    """R6: the ADMIN tier sits above the role matrix.

    The key's owner holds ``admin`` in the workspace, so a role-only check
    would let the write through; the governance gate must not.
    """
    result = _dispatch(
        "tree_display_config.set",
        {
            "scope": "workspace",
            "item_type": "Requirement",
            "fields": ["uid"],
            "workspace_id": str(e2e_workspace.id),
        },
        author_key_admin,
    )

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    # Fail-closed: the denied call wrote nothing.
    assert (
        TreeDisplayConfig.unscoped.filter(
            scope=TREE_DISPLAY_SCOPE_WORKSPACE, workspace_id=e2e_workspace.id
        ).count()
        == 0
    )


@pytest.mark.django_db
def test_author_key_of_an_admin_owner_may_not_set_the_global_default(
    author_key_admin: str, e2e_workspace, e2e_userrole_admin
) -> None:
    result = _dispatch(
        "tree_display_config.set",
        {"scope": "global", "item_type": "Requirement", "fields": ["uid"]},
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
        "tree_display_config.set",
        {"scope": "user", "item_type": "Requirement", "fields": ["uid"]},
        author_key_admin,
    )

    assert result.success is True, result
    assert result.data["scope"] == "user"


@pytest.mark.django_db
def test_admin_key_may_set_the_workspace_and_global_defaults(
    admin_key_admin: str, e2e_workspace, e2e_userrole_admin
) -> None:
    workspace_result = _dispatch(
        "tree_display_config.set",
        {
            "scope": "workspace",
            "item_type": "Requirement",
            "fields": ["uid"],
            "workspace_id": str(e2e_workspace.id),
        },
        admin_key_admin,
    )
    global_result = _dispatch(
        "tree_display_config.set",
        {"scope": "global", "item_type": "Requirement", "fields": ["uid"]},
        admin_key_admin,
    )

    assert workspace_result.success is True, workspace_result
    assert global_result.success is True, global_result
    assert TreeDisplayConfig.unscoped.filter(
        scope=TREE_DISPLAY_SCOPE_WORKSPACE, workspace_id=e2e_workspace.id
    ).exists()
    assert TreeDisplayConfig.unscoped.filter(scope="global").exists()
