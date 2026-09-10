"""A read-scoped API key may not write, whatever its RBAC roles say."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from rest_framework import exceptions

from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.services import Operation
from rest_api.auth_enforcer import RbacPermission


def _ctx(scope: str) -> AuthContext:
    return AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid4(),
        actor_type="agent",
        agent_label="Bot",
        scope=scope,
    )


class _View:
    required_operation = None


def _request(method: str, ctx: AuthContext):
    return SimpleNamespace(method=method, auth_context=ctx)


def test_read_scope_allows_get():
    assert RbacPermission().has_permission(_request("GET", _ctx("read")), _View())


def test_read_scope_denies_post():
    with pytest.raises(exceptions.PermissionDenied) as exc:
        RbacPermission().has_permission(_request("POST", _ctx("read")), _View())
    assert "read-only" in str(exc.value).lower()


def test_read_scope_denies_declared_write_operation():
    view = _View()
    view.required_operation = Operation.WORKFLOW_TRANSITION
    with pytest.raises(exceptions.PermissionDenied):
        RbacPermission().has_permission(_request("GET", _ctx("read")), view)


def test_write_scope_allows_post():
    assert RbacPermission().has_permission(_request("POST", _ctx("write")), _View())
