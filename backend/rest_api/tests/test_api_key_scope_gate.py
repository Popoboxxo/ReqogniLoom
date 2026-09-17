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


# --- #917 -------------------------------------------------------------------
# ``required_operation`` is an RBAC-matrix knob and may LOWER the requirement
# for a self-service action: ``ApiKeyViewSet`` declares READ on a ViewSet whose
# POST creates a key (#716) so a Viewer can manage their own keys. It must not
# lower the API-key capability gate — before the fix the scope gate was fed that
# READ declaration, so a read-scoped key's POST passed the gate and reached the
# view body (where the per-user key limit answered 400 instead of this 403).


def test_read_scope_denies_post_when_view_declares_read_operation():
    view = _View()
    view.required_operation = Operation.READ
    with pytest.raises(exceptions.PermissionDenied) as exc:
        RbacPermission().has_permission(_request("POST", _ctx("read")), view)
    message = str(exc.value)
    assert "read-only" in message.lower()
    # The method-derived operation names the reason the caller must see.
    assert "operation 'write'" in message


def test_read_scope_allows_get_when_view_declares_read_operation():
    """The stricter gate still permits the read the declaration was made for."""
    view = _View()
    view.required_operation = Operation.READ
    assert RbacPermission().has_permission(_request("GET", _ctx("read")), view)


def test_read_scope_denies_delete_when_view_declares_read_operation():
    """Revoking a key is a write too (DELETE 204 path of the same ViewSet)."""
    view = _View()
    view.required_operation = Operation.READ
    with pytest.raises(exceptions.PermissionDenied):
        RbacPermission().has_permission(_request("DELETE", _ctx("read")), view)


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
