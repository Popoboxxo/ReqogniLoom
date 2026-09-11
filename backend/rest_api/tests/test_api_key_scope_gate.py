"""A read-scoped API key may not write, whatever its RBAC roles say."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from rest_framework import exceptions

from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.rest import HasOperationPermission
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


# --- Security review B1 -----------------------------------------------------
# ~25 views use HasOperationPermission INSTEAD of RbacPermission. The scope gate
# lived only in the latter, so those views let a read-scoped key write.


def test_has_operation_permission_read_scope_denies_post_without_declared_op():
    # The dangerous case: no ``required_operation``, so the class used to
    # short-circuit to "authenticated is enough" before any gate ran.
    with pytest.raises(exceptions.PermissionDenied) as exc:
        HasOperationPermission().has_permission(
            _request("POST", _ctx("read")), _View()
        )
    assert "read-only" in str(exc.value).lower()


def test_has_operation_permission_read_scope_denies_declared_write():
    view = _View()
    view.required_operation = Operation.WRITE
    with pytest.raises(exceptions.PermissionDenied):
        HasOperationPermission().has_permission(_request("GET", _ctx("read")), view)


def test_has_operation_permission_read_scope_allows_get():
    assert HasOperationPermission().has_permission(
        _request("GET", _ctx("read")), _View()
    )


def test_has_operation_permission_write_scope_allows_post():
    assert HasOperationPermission().has_permission(
        _request("POST", _ctx("write")), _View()
    )


def test_bearer_token_without_scope_is_unaffected():
    # JWT bearer callers carry scope=None; the gate must never touch them.
    ctx = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    assert RbacPermission().has_permission(_request("POST", ctx), _View())
    assert HasOperationPermission().has_permission(_request("POST", ctx), _View())
