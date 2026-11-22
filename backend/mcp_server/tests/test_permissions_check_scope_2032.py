"""#2032 — permissions.check reports the key scope, not just the RBAC role."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from application.effective_permission_service import EffectivePermission
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import ITEM_PERMISSION_WRITE
from auth_tenancy.services.item_permission import PermissionDecision
from mcp_server.tools.permissions import PermissionsToolGroup

WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000010")


def _ctx(scope: str) -> AuthContext:
    return AuthContext(
        user_id=UUID("00000000-0000-0000-0000-000000000001"),
        tenant_id=UUID("00000000-0000-0000-0000-000000000002"),
        active_roles=("admin",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=UUID("00000000-0000-0000-0000-000000000003"),
        scope=scope,
    )


def _check(scope: str, level: str = "write"):
    item = MagicMock()
    item.check_permission.return_value = PermissionDecision(
        level=ITEM_PERMISSION_WRITE, reason="artifact-scoped rule grants 'write'"
    )
    return PermissionsToolGroup(service=item).execute_tool(
        "permissions.check",
        params={"workspace_id": str(WORKSPACE_ID), "permission_level": level},
        auth_context=_ctx(scope),
        api_key="reqlo_test_key",
    )


def test_author_scope_exposes_governance_false():
    result = _check("author")
    assert result.success is True
    assert result.data["decision"]["is_allowed"] is True
    assert result.data["key_scope"] == "author"
    assert result.data["governance_allowed"] is False
    assert "governance" in result.data["decision"]["reason"].lower()


def test_admin_scope_exposes_governance_true():
    result = _check("admin")
    assert result.data["governance_allowed"] is True
    assert result.data["key_scope"] == "admin"


def test_read_only_key_cannot_report_write_allowed():
    result = _check("read_only")
    assert result.data["decision"]["is_allowed"] is False
    assert result.data["decision"]["level"] == "read"
    assert result.data["governance_allowed"] is False


def test_decision_subdict_shape_is_unchanged():
    assert set(_check("author").data["decision"]) == {"level", "reason", "is_allowed"}


@pytest.mark.parametrize("scope", ["author", "read_only", "write"])
def test_scope_is_forwarded_to_layer2_service(scope):
    with patch.object(
        PermissionsToolGroup, "_effective_permissions"
    ) as factory:
        resolver = MagicMock()
        resolver.resolve_effective_permission.return_value = EffectivePermission(
            level="write", reason="rbac", is_allowed=True, queried_level="write"
        )
        factory.return_value = resolver
        _check(scope)
    kwargs = resolver.resolve_effective_permission.call_args.kwargs
    assert kwargs["scope"] == scope
    assert kwargs["level"] == "write"
