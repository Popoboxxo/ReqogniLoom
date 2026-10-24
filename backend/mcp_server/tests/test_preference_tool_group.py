"""MCP ``preference.*`` tool group — Q1 three-level preferences (Plan C, T-C2-4).

The four handlers are thin wrappers over ``PreferenceService`` (Layer 2); these
tests pin the published surface, the classification gates the rest of the MCP
suite depends on (read-exempt list, ADMIN-tier governance write, workspace-scope
coverage), and the three security/validation contracts of the task:

* an AUTHOR-tier key whose *owner* is an admin is still denied
  ``preference.set_default(scope="global")`` — the tier gate is above the role
  matrix, so a privileged owner cannot lend it away;
* ``preference.set`` accepts only its own documented parameters (a stray
  ``scope`` is a validation error, not a silently ignored key — otherwise a
  caller would believe it just wrote a workspace default);
* ``preference.get`` with a workspace the caller holds no role in answers
  access-denied and leaks no value.

Tool-name checks are set membership (``"preference.set_default" in tool_names``),
never catalogue totals: several parallel tool PRs share the manifest (§f.1), so
an absolute number would be a merge conflict rather than a regression signal.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import PreferenceValue
from auth_tenancy.services import Operation
from auth_tenancy.services.authentication import AuthenticationService
from mcp_server.tool_registry import ToolRegistry
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, Workspace
from presets.models import WorkspacePresetConfig

TOOL_NAMES = (
    "preference.registry",
    "preference.get",
    "preference.set",
    "preference.set_default",
)


def _dispatch(tool_name: str, params: dict[str, Any], api_key: str):
    return ToolRegistry().dispatch_request(
        tool_name=tool_name, params=params, api_key=api_key
    )


def _group():
    from mcp_server.tools.preference import PreferenceToolGroup

    return PreferenceToolGroup()


def _ctx(scope: str = "author", roles: tuple[str, ...] = ("admin",)) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=roles,
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid.uuid4(),
        actor_type="agent",
        agent_label="preference-test",
        scope=scope,
    )


def _call(tool_name: str, params: dict[str, Any], ctx: AuthContext | None = None):
    return _group().execute_tool(
        tool_name=tool_name,
        params=params,
        auth_context=ctx or _ctx(),
        api_key="reqlo_test_key",
    )


# ---------------------------------------------------------------------------
# Fixtures (DB-backed dispatch tests)
# ---------------------------------------------------------------------------


def _make_workspace(tenant: Tenant, name: str, preset: dict[str, Any]) -> Workspace:
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=name, is_active=True, preset=preset
        )
    finally:
        clear_request_tenant()
    WorkspacePresetConfig.unscoped.create(
        tenant=tenant,
        workspace=workspace,
        active_tier="extended",
        terminology_profile="dev_mode",
        downgrade_policy="allow",
    )
    return workspace


@pytest.fixture
def foreign_workspace(e2e_tenant: Tenant, e2e_preset: dict[str, Any]) -> Workspace:
    """Workspace B — same tenant, no role for any e2e user."""
    return _make_workspace(e2e_tenant, "Preference Foreign Workspace B", e2e_preset)


@pytest.fixture
def author_key_admin(e2e_tenant: Tenant, e2e_user_admin) -> str:
    """An AUTHOR-tier agent key whose owner is an admin in the e2e workspace.

    The tier is a property of the key, not of the owner — this fixture is what
    makes the "privileged owner, narrow key" case testable end to end.
    """
    return (
        AuthenticationService()
        .create_api_key(
            user_id=e2e_user_admin.id,
            tenant_id=e2e_tenant.id,
            name=f"pref-author-{uuid.uuid4().hex[:8]}",
            scope="author",
            expires_at=timezone.now() + timedelta(days=1),
        )
        .plaintext
    )


# ---------------------------------------------------------------------------
# Published surface
# ---------------------------------------------------------------------------


def test_group_publishes_exactly_the_four_contract_tools() -> None:
    group = _group()
    names = {schema["name"] for schema in group._TOOL_SCHEMAS}
    assert names == set(TOOL_NAMES)
    assert set(group._TOOL_MAP) == names
    for handler in group._TOOL_MAP.values():
        assert hasattr(group, handler)


def test_get_schema_offers_the_effective_and_level_scopes() -> None:
    schema = next(
        s for s in _group()._TOOL_SCHEMAS if s["name"] == "preference.get"
    )
    assert set(schema["inputSchema"]["properties"]["scope"]["enum"]) == {
        "effective",
        "user",
        "workspace",
        "global",
    }
    assert "required" not in schema["inputSchema"]


def test_set_schema_takes_values_only() -> None:
    schema = next(
        s for s in _group()._TOOL_SCHEMAS if s["name"] == "preference.set"
    )
    assert schema["inputSchema"]["required"] == ["values"]
    # No scope/workspace_id/user_id: a user-level write is addressed by the
    # credential alone. Rejecting them here is what keeps `set` off the
    # governance path.
    assert set(schema["inputSchema"]["properties"]) == {"values"}


def test_set_default_schema_takes_workspace_or_global_scope() -> None:
    schema = next(
        s for s in _group()._TOOL_SCHEMAS if s["name"] == "preference.set_default"
    )
    assert schema["inputSchema"]["required"] == ["scope", "values"]
    assert schema["inputSchema"]["properties"]["scope"]["enum"] == [
        "workspace",
        "global",
    ]

def test_all_four_tools_are_in_the_registry_catalogue(db) -> None:
    """Membership only — an absolute total would collide with parallel tool PRs."""
    from mcp_server.management.commands.export_tool_manifest import build_manifest

    tool_names = {tool["name"] for tool in build_manifest()["tools"]}
    for name in TOOL_NAMES:
        assert name in tool_names


# ---------------------------------------------------------------------------
# Registry classification
# ---------------------------------------------------------------------------


def test_group_is_registered_and_split_read_write(db) -> None:
    registry = ToolRegistry()
    registry._ensure_groups()

    assert "preference" in registry._groups
    assert registry._is_write_tool("preference.registry") is False
    assert registry._is_write_tool("preference.get") is False
    assert registry._is_write_tool("preference.set") is True
    assert registry._is_write_tool("preference.set_default") is True


def test_scope_tiers_match_the_rest_rule() -> None:
    registry = ToolRegistry()
    assert registry._required_scope_operation("preference.registry") is Operation.READ
    assert registry._required_scope_operation("preference.get") is Operation.READ
    assert registry._required_scope_operation("preference.set") is Operation.WRITE
    assert (
        registry._required_scope_operation("preference.set_default")
        is Operation.WORKSPACE_CONFIG
    )


def test_reads_are_classified_for_workspace_scope_coverage() -> None:
    """The coverage ratchet in test_mcp_workspace_scope.py needs these entries."""
    from mcp_server.workspace_scope import TENANT_SCOPED_READ_TOOLS

    assert "preference.registry" in TENANT_SCOPED_READ_TOOLS
    assert "preference.get" in TENANT_SCOPED_READ_TOOLS
    # The writes must never be misclassified as tenant-wide reads.
    assert "preference.set" not in TENANT_SCOPED_READ_TOOLS
    assert "preference.set_default" not in TENANT_SCOPED_READ_TOOLS


# ---------------------------------------------------------------------------
# Parameter validation
# ---------------------------------------------------------------------------


def test_set_rejects_a_scope_parameter() -> None:
    """``preference.set`` is user-level only; a stray ``scope`` is an error."""
    result = _call(
        "preference.set",
        {"scope": "workspace", "values": {"ui.ids.show_readable": False}},
    )
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "Unknown parameter" in str(result.message)
    assert "scope" in str(result.message)


def test_set_rejects_a_workspace_id_parameter() -> None:
    result = _call(
        "preference.set",
        {"workspace_id": str(uuid.uuid4()), "values": {}},
    )
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_set_default_rejects_the_user_scope() -> None:
    result = _call(
        "preference.set_default",
        {"scope": "user", "values": {"ui.ids.show_readable": False}},
    )
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_set_default_workspace_requires_a_workspace_id() -> None:
    result = _call(
        "preference.set_default",
        {"scope": "workspace", "values": {"ui.ids.show_readable": False}},
    )
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_get_rejects_workspace_scope_without_a_workspace_id() -> None:
    result = _call("preference.get", {"scope": "workspace"})
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_registry_rejects_an_unknown_parameter() -> None:
    result = _call("preference.registry", {"scope": "global"})
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# End-to-end dispatch: tier, write path, read gate
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_author_key_of_an_admin_owner_is_denied_the_global_default(
    author_key_admin: str,
    e2e_workspace: Workspace,
    e2e_userrole_admin,
) -> None:
    """The capability tier sits above the role matrix (R6 / ENT-C3 = B).

    The key's owner is an admin in *e2e_workspace*, so a role-only check would
    let the write through; the ADMIN-tier gate must not.
    """
    result = _dispatch(
        "preference.set_default",
        {"scope": "global", "values": {"ui.ids.show_readable": False}},
        author_key_admin,
    )

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    assert "governance" in str(result.message).lower()
    # Fail-closed: the denied call wrote nothing.
    assert (
        PreferenceValue.unscoped.filter(
            scope="global", key="ui.ids.show_readable"
        ).count()
        == 0
    )


@pytest.mark.django_db
def test_set_writes_the_user_level_and_get_resolves_it(
    author_key_admin: str,
    e2e_workspace: Workspace,
    e2e_userrole_admin,
) -> None:
    written = _dispatch(
        "preference.set",
        {"values": {"ui.ids.show_readable": False}},
        author_key_admin,
    )
    assert written.success is True
    assert written.data["scope"] == "user"
    assert written.data["values"]["ui.ids.show_readable"] is False

    read = _dispatch("preference.get", {"scope": "effective"}, author_key_admin)
    assert read.success is True
    assert read.data["values"]["ui.ids.show_readable"] == {
        "value": False,
        "source": "user",
    }


@pytest.mark.django_db
def test_registry_answers_the_core_keys(author_key_admin: str) -> None:
    result = _dispatch("preference.registry", {}, author_key_admin)
    assert result.success is True
    keys = {entry["key"] for entry in result.data["keys"]}
    assert "ui.ids.show_readable" in keys


@pytest.mark.django_db
def test_get_is_denied_for_a_workspace_without_a_role(
    e2e_api_key_admin: str,
    e2e_workspace: Workspace,
    e2e_userrole_admin,
    foreign_workspace: Workspace,
) -> None:
    """A foreign workspace is an access error, not an empty answer."""
    result = _dispatch(
        "preference.get",
        {"scope": "effective", "workspace_id": str(foreign_workspace.id)},
        e2e_api_key_admin,
    )

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    assert "read access" in str(result.message)
    assert not result.data.get("values")
