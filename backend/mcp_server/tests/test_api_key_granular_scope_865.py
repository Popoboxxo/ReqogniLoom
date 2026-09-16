"""Granular API-key scopes on the MCP surface (#865).

The MCP dispatcher maps each tool onto the same ``Operation`` vocabulary the
REST adapters gate on, so one shared capability gate decides both transports:
read tools need the READ tier, content writes the AUTHOR tier, and governance
namespaces (``user.*``, ``admin.*``, ``baseline.create``, ...) the ADMIN tier —
including on the RBAC-exempt paths, which must never widen a key's capability.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, Dict

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.services import Operation
from mcp_server.protocol_handler import ToolResult
from mcp_server.tool_registry import ToolRegistry


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


def _registry(scope: str, monkeypatch) -> tuple[ToolRegistry, _StubGroup, _StubGroup]:
    """A registry whose auth/roles are stubbed, with content + governance stubs."""
    registry = ToolRegistry()
    content = _StubGroup("requirement.create", "requirement.get")
    governance = _StubGroup("user.create", "baseline.create", "admin.restore")
    registry.register_groups({"requirement": content, "user": governance,
                               "baseline": governance, "admin": governance})
    ctx = _ctx(scope)
    monkeypatch.setattr(registry, "_validate_api_key", lambda _key: (ctx, None))
    monkeypatch.setattr(registry, "_resolve_roles", lambda c, _ws: c)
    return registry, content, governance


# ---------------------------------------------------------------------------
# Tool -> tier classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tool_name", "expected"),
    [
        ("requirement.get", Operation.READ),
        ("admin.backup_list", Operation.READ),
        ("events.dlq_list", Operation.READ),
        ("user.list", Operation.READ),
        ("workspace.get_context", Operation.READ),
        ("baseline.get", Operation.READ),
        # Governance namespaces stay READ-tier for reads (follow-up to #865).
        ("prompt_template.get", Operation.READ),
        ("prompt_variable.list", Operation.READ),
        ("link_type.list", Operation.READ),
        ("attribute_definition.list", Operation.READ),
        ("attribute_catalog.list", Operation.READ),
        ("attribute_migration.list_runs", Operation.READ),
        ("requirement.create", Operation.WRITE),
        ("test.update", Operation.WRITE),
        ("test.run_create", Operation.WRITE),
        ("user.create", Operation.WORKSPACE_CONFIG),
        ("user.assign_role", Operation.WORKSPACE_CONFIG),
        ("baseline.create", Operation.WORKSPACE_CONFIG),
        ("admin.restore", Operation.WORKSPACE_CONFIG),
        ("workspace.delete", Operation.WORKSPACE_CONFIG),
        ("permissions.set_rule", Operation.WORKSPACE_CONFIG),
        ("events.dlq_replay", Operation.WORKSPACE_CONFIG),
        # Follow-up to #865: governance *configuration* namespaces are ADMIN
        # tier as well. Their earlier protection was a service-internal
        # admin-role check, which does not narrow an AUTHOR-tier key whose owner
        # legitimately holds that role — and prompt content is the persistent
        # prompt-injection vector (REQ-043). Symmetry with
        # ``rest_api.settings_views``, which declares the same tier on REST.
        ("link_type.create", Operation.WORKSPACE_CONFIG),
        ("attribute_migration.apply", Operation.WORKSPACE_CONFIG),
        ("prompt_template.update", Operation.WORKSPACE_CONFIG),
        ("prompt_variable.set", Operation.WORKSPACE_CONFIG),
        ("attribute_definition.update", Operation.WORKSPACE_CONFIG),
        ("attribute_catalog.update", Operation.WORKSPACE_CONFIG),
    ],
)
def test_required_scope_operation_classification(tool_name, expected) -> None:
    assert ToolRegistry()._required_scope_operation(tool_name) is expected


def test_unknown_namespace_is_content_tier() -> None:
    """A new content namespace must not need an ADMIN key to write."""
    assert ToolRegistry()._required_scope_operation("widget.create") is Operation.WRITE


# ---------------------------------------------------------------------------
# _check_rbac backstop
# ---------------------------------------------------------------------------


def test_check_rbac_denies_author_on_governance_tool() -> None:
    message = ToolRegistry()._check_rbac(_ctx("author"), "user.create")
    assert message is not None
    assert "admin" in message


def test_check_rbac_allows_author_on_content_tool() -> None:
    assert ToolRegistry()._check_rbac(_ctx("author"), "requirement.create") is None


def test_check_rbac_without_tool_name_stays_write_only() -> None:
    """Existing callers/tests call it without a name; behaviour is unchanged."""
    assert ToolRegistry()._check_rbac(_ctx("author")) is None
    assert ToolRegistry()._check_rbac(_ctx("read")) is not None


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_author_scope_dispatches_content_write(monkeypatch) -> None:
    registry, content, _governance = _registry("author", monkeypatch)
    result = registry.dispatch_request(
        tool_name="requirement.create",
        params={"title": "x", "description": "y"},
        api_key="reqlo_x",
    )
    assert result.success is True
    assert content.calls == ["requirement.create"]


@pytest.mark.django_db
def test_author_scope_denied_on_governance_tool(monkeypatch) -> None:
    registry, _content, governance = _registry("author", monkeypatch)
    result = registry.dispatch_request(
        tool_name="user.create", params={"username": "x"}, api_key="reqlo_x"
    )
    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    assert "admin" in str(result.message)
    assert governance.calls == []


@pytest.mark.django_db
def test_author_scope_denied_on_rbac_exempt_governance_tool(monkeypatch) -> None:
    """Tenant-admin/bootstrap exemptions never widen the capability tier (B2)."""
    registry, _content, _governance = _registry("author", monkeypatch)
    monkeypatch.setattr(registry, "_is_bootstrap_candidate", lambda *a, **k: True)
    monkeypatch.setattr(registry, "_is_tenant_admin_exempt", lambda *a, **k: True)
    result = registry.dispatch_request(
        tool_name="admin.restore", params={}, api_key="reqlo_x"
    )
    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


@pytest.mark.django_db
def test_admin_scope_dispatches_governance_tool(monkeypatch) -> None:
    registry, _content, governance = _registry("admin", monkeypatch)
    result = registry.dispatch_request(
        tool_name="user.create", params={"username": "x"}, api_key="reqlo_x"
    )
    assert result.success is True
    assert governance.calls == ["user.create"]


@pytest.mark.django_db
def test_legacy_write_scope_still_dispatches_governance_tool(monkeypatch) -> None:
    registry, _content, governance = _registry("write", monkeypatch)
    result = registry.dispatch_request(
        tool_name="baseline.create", params={}, api_key="reqlo_x"
    )
    assert result.success is True
    assert governance.calls == ["baseline.create"]


@pytest.mark.django_db
def test_read_only_scope_denied_on_content_write(monkeypatch) -> None:
    registry, content, _governance = _registry("read", monkeypatch)
    result = registry.dispatch_request(
        tool_name="requirement.create", params={"title": "x"}, api_key="reqlo_x"
    )
    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    assert "read-only" in str(result.message).lower()
    assert content.calls == []


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
    ("scope", "expect_content", "expect_governance"),
    [
        ("read_only", False, False),
        ("author", True, False),
        ("admin", True, True),
        # Legacy aliases keep their exact previous visibility.
        ("read", False, False),
        ("write", True, True),
    ],
)
def test_tools_list_hides_what_the_scope_cannot_execute(
    scope: str, expect_content: bool, expect_governance: bool, monkeypatch
) -> None:
    registry = ToolRegistry()
    registry.register_groups(
        {
            "requirement": _StubGroup("requirement.create", "requirement.get"),
            "user": _StubGroup("user.create", "user.list"),
        }
    )

    names = _listed(registry, scope, monkeypatch)

    assert ("requirement.get" in names) is True
    assert ("requirement.create" in names) is expect_content
    assert ("user.create" in names) is expect_governance
