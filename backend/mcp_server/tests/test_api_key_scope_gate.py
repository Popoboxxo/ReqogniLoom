"""MCP honours ApiKey.scope and preserves agent identity across role resolution."""
from __future__ import annotations

from uuid import uuid4

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tool_registry import ToolRegistry


def _ctx(scope: str = "write", actor_type: str = "agent") -> AuthContext:
    return AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid4(),
        actor_type=actor_type,
        agent_label="Claude Code",
        scope=scope,
    )


def test_check_rbac_denies_read_scope():
    msg = ToolRegistry()._check_rbac(_ctx(scope="read"))
    assert msg is not None
    assert "read-only" in msg.lower()


def test_check_rbac_allows_write_scope():
    assert ToolRegistry()._check_rbac(_ctx(scope="write")) is None


@pytest.mark.django_db
def test_resolve_roles_preserves_agent_identity():
    registry = ToolRegistry()
    resolved = registry._resolve_roles(_ctx(), workspace_id=None)
    assert resolved.actor_type == "agent"
    assert resolved.agent_label == "Claude Code"
    assert resolved.scope == "write"


# --- Security review B2 -----------------------------------------------------
# The scope check used to live INSIDE _check_rbac, which the two RBAC
# exemptions (_is_bootstrap_candidate / _is_tenant_admin_exempt) skip
# wholesale — so a read-scoped key on an exempt path wrote unchecked.


def _read_scoped_dispatch(monkeypatch, tool_name: str, params: dict):
    """Dispatch *tool_name* as an admin whose key is read-scoped."""
    registry = ToolRegistry()
    ctx = _ctx(scope="read")
    monkeypatch.setattr(registry, "_validate_api_key", lambda _key: (ctx, None))
    monkeypatch.setattr(registry, "_resolve_roles", lambda c, _ws: c)
    # Force both exemption branches on, so the test proves the scope gate
    # stands on its own rather than riding on the RBAC gate behind it.
    monkeypatch.setattr(registry, "_is_bootstrap_candidate", lambda *a, **k: True)
    monkeypatch.setattr(registry, "_is_tenant_admin_exempt", lambda *a, **k: True)
    return registry.dispatch_request(
        tool_name=tool_name, params=params, api_key="reqlo_x"
    )


@pytest.mark.django_db
def test_read_scope_denied_on_rbac_exempt_write_path(monkeypatch):
    result = _read_scoped_dispatch(
        monkeypatch, "requirement.create", {"title": "x", "description": "y"}
    )
    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    assert "read-only" in str(result.message).lower()


# --- Security review B3 -----------------------------------------------------
# ApiKey.workspace_ids fences a key to named workspaces. REST inherits the
# fence from TenantContextService.build_auth_context; MCP builds its own
# AuthContext and never checked it.


def _fenced_ctx(*workspace_ids: str) -> AuthContext:
    return AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid4(),
        actor_type="agent",
        agent_label="Claude Code",
        scope="write",
        api_key_workspace_ids=tuple(workspace_ids),
    )


def test_unfenced_key_passes_every_workspace():
    check = ToolRegistry()._check_workspace_fence
    assert check(_fenced_ctx(), str(uuid4())) is None
    assert check(_fenced_ctx(), None) is None


def test_fenced_key_passes_its_own_workspace():
    allowed = str(uuid4())
    assert ToolRegistry()._check_workspace_fence(_fenced_ctx(allowed), allowed) is None


def test_fenced_key_denied_on_foreign_workspace():
    msg = ToolRegistry()._check_workspace_fence(_fenced_ctx(str(uuid4())), str(uuid4()))
    assert msg is not None
    assert "restricted" in msg.lower()


def test_fenced_key_denied_without_resolvable_workspace():
    # Fail closed, mirroring TenantContextService.build_auth_context: with no
    # target there is nothing to check the fence against.
    assert ToolRegistry()._check_workspace_fence(_fenced_ctx(str(uuid4())), None)


@pytest.mark.django_db
def test_fenced_key_denied_end_to_end(monkeypatch):
    registry = ToolRegistry()
    ctx = _fenced_ctx(str(uuid4()))
    monkeypatch.setattr(registry, "_validate_api_key", lambda _key: (ctx, None))
    monkeypatch.setattr(registry, "_resolve_roles", lambda c, _ws: c)
    monkeypatch.setattr(registry, "_workspace_exists_fn", lambda _ws: True)

    result = registry.dispatch_request(
        tool_name="requirement.create",
        params={"workspace_id": str(uuid4()), "title": "x", "description": "y"},
        api_key="reqlo_x",
    )
    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


@pytest.mark.django_db
def test_fenced_key_sees_no_write_tools_in_list(monkeypatch):
    registry = ToolRegistry()
    assert registry._resolve_list_roles(_fenced_ctx(str(uuid4())), None) == ()
    allowed = str(uuid4())
    monkeypatch.setattr(
        registry, "_resolve_roles", lambda c, _ws: _fenced_ctx(allowed)
    )
    assert registry._resolve_list_roles(_fenced_ctx(allowed), allowed) == ("admin",)
