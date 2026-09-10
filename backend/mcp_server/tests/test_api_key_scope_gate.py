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
