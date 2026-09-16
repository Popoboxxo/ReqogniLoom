"""Governance configuration namespaces require the ADMIN tier on MCP (#865 follow-up).

The security review of #865 found six namespaces still only AUTHOR-tier because
their protection is a service-internal admin-*role* assertion
(``prompt_template``, ``prompt_variable``, ``link_type``,
``attribute_definition``, ``attribute_catalog``, ``attribute_migration``). A role
check does not narrow an AUTHOR-tier key whose *owner* holds the Admin role — and
prompt content is the canonical persistent prompt-injection vector (REQ-043), so
the capability tier has to deny it. Symmetric with ``rest_api.settings_views``,
which declares the same tier on REST, so neither transport is a hole for the
other.

Covers: the name -> tier classification of the newly governed namespaces, the
``_check_rbac`` backstop, dispatch with real and stubbed credentials, the
``tools/list`` surface, and an end-to-end pass with real API keys against the
real ``prompt_template.update`` handler.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, Dict

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import ROLE_ADMIN, UserRole
from auth_tenancy.services import Operation
from auth_tenancy.services.authentication import AuthenticationService
from mcp_server.protocol_handler import ToolResult
from mcp_server.tool_registry import ToolRegistry
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import PromptTemplate, Tenant, User, Workspace

#: Write tools of the namespaces this follow-up moves to the ADMIN tier. Every
#: one of them is name-classified as a write by the fail-closed default, so the
#: namespace is what decides the tier.
_GOVERNANCE_WRITE_TOOLS = (
    "prompt_template.create",
    "prompt_template.update",
    "prompt_variable.set",
    "prompt_variable.clear",
    "link_type.create",
    "link_type.update",
    "link_type.reset",
    "attribute_definition.create",
    "attribute_definition.update",
    "attribute_catalog.update",
    "attribute_migration.apply",
)

_GOVERNANCE_NAMESPACES = tuple(
    sorted({name.split(".", 1)[0] for name in _GOVERNANCE_WRITE_TOOLS})
)


def _ctx(scope: str = "write") -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid.uuid4(),
        actor_type="agent",
        agent_label="Claude Code",
        scope=scope,
    )


class _StubGroup:
    """Records executions so a test can prove a call never reached the tool."""

    def __init__(self, *tool_names: str) -> None:
        self.tool_names = tool_names
        self.calls: list[str] = []

    def get_tool_schemas(self) -> list[Dict[str, Any]]:
        return [{"name": name, "description": name} for name in self.tool_names]

    def execute_tool(self, *, tool_name: str, params: Any, auth_context: Any, api_key: str):
        self.calls.append(tool_name)
        return ToolResult.ok({"tool": tool_name})


def _registry(
    scope: str, monkeypatch
) -> tuple[ToolRegistry, _StubGroup, _StubGroup]:
    """A registry whose auth/roles are stubbed, with content + governance stubs."""
    registry = ToolRegistry()
    content = _StubGroup("requirement.create", "requirement.get")
    governance = _StubGroup("prompt_template.get", *_GOVERNANCE_WRITE_TOOLS)
    groups: Dict[str, Any] = {"requirement": content}
    groups.update({namespace: governance for namespace in _GOVERNANCE_NAMESPACES})
    registry.register_groups(groups)
    ctx = _ctx(scope)
    monkeypatch.setattr(registry, "_validate_api_key", lambda _key: (ctx, None))
    monkeypatch.setattr(registry, "_resolve_roles", lambda c, _ws: c)
    return registry, content, governance


# ---------------------------------------------------------------------------
# Tool -> tier classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool_name", _GOVERNANCE_WRITE_TOOLS)
def test_governance_configuration_writes_are_admin_tier(tool_name: str) -> None:
    """The six namespaces resolve to the ADMIN tier, exactly like ``user.*``."""
    assert ToolRegistry()._required_scope_operation(tool_name) is Operation.WORKSPACE_CONFIG


@pytest.mark.parametrize(
    "tool_name",
    [
        "prompt_template.get",
        "prompt_template.list",
        "prompt_variable.get",
        "prompt_variable.list",
        "link_type.get",
        "link_type.list",
        "attribute_definition.get",
        "attribute_definition.list",
        "attribute_catalog.list",
        "attribute_catalog.search",
        "attribute_migration.plan",
        "attribute_migration.list_runs",
    ],
)
def test_governance_configuration_reads_stay_read_tier(tool_name: str) -> None:
    """Reads in the newly governed namespaces need no ADMIN key (unchanged)."""
    assert ToolRegistry()._required_scope_operation(tool_name) is Operation.READ


# ---------------------------------------------------------------------------
# _check_rbac backstop
# ---------------------------------------------------------------------------


def test_check_rbac_denies_author_on_prompt_template_update() -> None:
    message = ToolRegistry()._check_rbac(_ctx("author"), "prompt_template.update")
    assert message is not None
    assert "admin" in message


def test_check_rbac_allows_author_on_content_tool() -> None:
    assert ToolRegistry()._check_rbac(_ctx("author"), "requirement.create") is None


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("tool_name", _GOVERNANCE_WRITE_TOOLS)
def test_author_scope_denied_on_governance_configuration_write(
    tool_name: str, monkeypatch
) -> None:
    registry, _content, governance = _registry("author", monkeypatch)

    result = registry.dispatch_request(
        tool_name=tool_name, params={"name": "n", "content": "c"}, api_key="reqlo_x"
    )

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    assert "admin" in str(result.message)
    assert governance.calls == []


@pytest.mark.django_db
@pytest.mark.parametrize("scope", ["read_only", "read"])
@pytest.mark.parametrize("tool_name", _GOVERNANCE_WRITE_TOOLS)
def test_read_tier_scope_denied_on_governance_configuration_write(
    tool_name: str, scope: str, monkeypatch
) -> None:
    """READ_ONLY (and its legacy alias) is denied too — by the same gate."""
    registry, _content, governance = _registry(scope, monkeypatch)

    result = registry.dispatch_request(
        tool_name=tool_name, params={"name": "n", "content": "c"}, api_key="reqlo_x"
    )

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    assert governance.calls == []


@pytest.mark.django_db
@pytest.mark.parametrize("scope", ["admin", "write"])
@pytest.mark.parametrize("tool_name", _GOVERNANCE_WRITE_TOOLS)
def test_admin_tier_scope_dispatches_governance_configuration_write(
    tool_name: str, scope: str, monkeypatch
) -> None:
    """ADMIN — and the legacy ``write`` alias of the same tier — is allowed."""
    registry, _content, governance = _registry(scope, monkeypatch)

    result = registry.dispatch_request(
        tool_name=tool_name, params={"name": "n", "content": "c"}, api_key="reqlo_x"
    )

    assert result.success is True, result.message
    assert governance.calls == [tool_name]


@pytest.mark.django_db
def test_author_scope_still_dispatches_content_write(monkeypatch) -> None:
    """The narrowing is governance-only: ordinary content writes are unchanged."""
    registry, content, _governance = _registry("author", monkeypatch)

    result = registry.dispatch_request(
        tool_name="requirement.create",
        params={"title": "x", "description": "y"},
        api_key="reqlo_x",
    )

    assert result.success is True
    assert content.calls == ["requirement.create"]


# ---------------------------------------------------------------------------
# tools/list — the advertised surface matches what the key may execute
# ---------------------------------------------------------------------------


def _listed(registry: ToolRegistry, scope: str, monkeypatch) -> set[str]:
    ctx = _ctx(scope)
    monkeypatch.setattr(registry, "_validate_api_key", lambda _key: (ctx, None))
    monkeypatch.setattr(registry, "_resolve_list_roles", lambda c, _ws: ("admin",))
    monkeypatch.setattr(
        registry._authz_service,
        "decide_access",
        lambda roles, operation: SimpleNamespace(allow=True),
    )
    return {t["name"] for t in registry.list_tools(api_key="reqlo_x")}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("scope", "expect_content_write", "expect_governance_write"),
    [
        ("read_only", False, False),
        ("author", True, False),
        ("admin", True, True),
        # Legacy aliases keep their exact previous visibility.
        ("read", False, False),
        ("write", True, True),
    ],
)
def test_tools_list_hides_governance_configuration_from_non_admin_keys(
    scope: str, expect_content_write: bool, expect_governance_write: bool, monkeypatch
) -> None:
    """An AUTHOR key is not even advertised ``prompt_template.update``."""
    registry, _content, _governance = _registry(scope, monkeypatch)

    names = _listed(registry, scope, monkeypatch)

    assert ("prompt_template.update" in names) is expect_governance_write
    assert ("requirement.create" in names) is expect_content_write
    # Reads stay listed for every tier, including inside governance namespaces.
    assert "prompt_template.get" in names


# ---------------------------------------------------------------------------
# End-to-end: real API keys, real tool group, real prompt-template handler
# ---------------------------------------------------------------------------


@pytest.fixture
def mcp_admin_identity(db):
    """A tenant whose single user holds the Admin role, plus a workspace."""
    tenant = Tenant.objects.create(
        name="MCP-GOV-T", slug=f"mcp-gov-{uuid.uuid4().hex[:8]}", is_active=True
    )
    set_request_tenant(tenant.id)
    try:
        user = User.objects.create(
            username=f"mcp-gov-{uuid.uuid4().hex[:8]}", email="mcp-gov@t.test", tenant=tenant
        )
        workspace = Workspace.objects.create(
            tenant=tenant, name="MCP-GOV-WS", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    return tenant, user, workspace


def _api_key(tenant: Tenant, user: User, scope: str) -> str:
    return AuthenticationService().create_api_key(
        user_id=user.id,
        tenant_id=tenant.id,
        name=f"mcp-gov-{scope}-{uuid.uuid4().hex[:6]}",
        scope=scope,
    ).plaintext


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("scope", "allowed"),
    [("author", False), ("read_only", False), ("read", False), ("admin", True), ("write", True)],
)
def test_prompt_template_update_end_to_end(mcp_admin_identity, scope, allowed) -> None:
    """The prompt-injection vector is ADMIN-tier on MCP for real API keys.

    The owner holds the Admin role, so the handler's own ``_check_admin`` would
    pass — the denial can only come from the capability tier, which is exactly
    the point of this follow-up.
    """
    tenant, user, _workspace = mcp_admin_identity
    key = _api_key(tenant, user, scope)
    name = f"gov_scope_probe_{scope}"
    content = f"injected-{scope} {{n}}"

    result = ToolRegistry().dispatch_request(
        tool_name="prompt_template.update",
        params={"name": name, "content": content},
        api_key=key,
    )

    set_request_tenant(tenant.id)
    try:
        stored = PromptTemplate.objects.filter(name=name, content=content).exists()
    finally:
        clear_request_tenant()

    if allowed:
        assert result.success is True, result.message
        assert stored is True
    else:
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        assert "admin" in str(result.message)
        assert stored is False
