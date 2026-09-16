"""Granular API-key scopes at the REST seams (#865).

Covers the three REST enforcement points of the capability gate:

* ``RbacPermission`` (``rest_api.auth_enforcer``),
* ``HasOperationPermission`` (``auth_tenancy.rest``),
* the new ``required_scope_operation`` declaration, which lets a view keep a
  deliberately low RBAC requirement (#716 self-service) while demanding a
  governance capability from the key (#865: creating a key must not be
  reachable by an AUTHOR-tier key that could mint a wider one).

Plus the governance choke point shared with MCP — the SE-Auditor baseline gate
override/waiver in ``BaselineFacade._assert_override_permission`` — and an
end-to-end pass over real requests with real API keys of every tier.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from rest_framework import exceptions
from rest_framework.test import APIClient

from application.base import PermissionDeniedError
from application.baseline_facade import BaselineFacade
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, UserRole
from auth_tenancy.rest import HasOperationPermission
from auth_tenancy.services import Operation
from auth_tenancy.services.authentication import AuthenticationService
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from rest_api.api_key_views import ApiKeyViewSet
from rest_api.auth_enforcer import RbacPermission


# ---------------------------------------------------------------------------
# Gate-level helpers
# ---------------------------------------------------------------------------


def _ctx(scope: str | None, roles: tuple[str, ...] = (ROLE_ADMIN,)) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=roles,
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid.uuid4(),
        actor_type="agent",
        agent_label="Bot",
        scope=scope if scope is not None else "write",
    )


class _View:
    required_operation = None
    required_scope_operation = None


def _request(method: str, ctx: AuthContext) -> SimpleNamespace:
    return SimpleNamespace(method=method, auth_context=ctx)


def _governance_view(operation: Operation = Operation.WORKSPACE_CONFIG) -> _View:
    view = _View()
    view.required_operation = operation
    return view


# ---------------------------------------------------------------------------
# RbacPermission
# ---------------------------------------------------------------------------


def test_author_scope_allows_normal_write() -> None:
    assert RbacPermission().has_permission(_request("POST", _ctx("author")), _View())


def test_author_scope_denies_governance_operation() -> None:
    with pytest.raises(exceptions.PermissionDenied) as exc:
        RbacPermission().has_permission(
            _request("POST", _ctx("author")), _governance_view()
        )
    assert "admin" in str(exc.value)


def test_author_scope_denies_governance_on_safe_method_too() -> None:
    """A declared governance operation is denied whatever the HTTP method is."""
    with pytest.raises(exceptions.PermissionDenied):
        RbacPermission().has_permission(
            _request("GET", _ctx("author")), _governance_view(Operation.ASSIGN_ROLE)
        )


def test_admin_scope_allows_governance_operation() -> None:
    assert RbacPermission().has_permission(
        _request("POST", _ctx("admin")), _governance_view()
    )


def test_legacy_write_scope_keeps_full_access() -> None:
    for operation in (Operation.WORKSPACE_CONFIG, Operation.ASSIGN_ROLE,
                      Operation.WORKFLOW_APPROVAL):
        assert RbacPermission().has_permission(
            _request("POST", _ctx("write")), _governance_view(operation)
        ), operation


def test_read_only_scope_still_denies_writes() -> None:
    with pytest.raises(exceptions.PermissionDenied) as exc:
        RbacPermission().has_permission(_request("POST", _ctx("read")), _View())
    assert "read-only" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# required_scope_operation — the #865 declaration
# ---------------------------------------------------------------------------


def test_required_scope_operation_narrows_every_method() -> None:
    """A plain attribute gates all methods, like ``required_operation`` does.

    A view that wants reads left open declares the property conditionally (see
    ``ApiKeyViewSet.required_scope_operation``).
    """
    view = _View()
    view.required_scope_operation = Operation.ASSIGN_ROLE
    with pytest.raises(exceptions.PermissionDenied):
        RbacPermission().has_permission(_request("POST", _ctx("author")), view)
    with pytest.raises(exceptions.PermissionDenied):
        RbacPermission().has_permission(_request("GET", _ctx("author")), view)


def test_required_scope_operation_allows_admin_scope() -> None:
    view = _View()
    view.required_scope_operation = Operation.ASSIGN_ROLE
    assert RbacPermission().has_permission(_request("POST", _ctx("admin")), view)


def test_has_operation_permission_honours_required_scope_operation() -> None:
    view = _View()
    view.required_scope_operation = Operation.WORKSPACE_CONFIG
    with pytest.raises(exceptions.PermissionDenied):
        HasOperationPermission().has_permission(_request("POST", _ctx("author")), view)
    assert HasOperationPermission().has_permission(
        _request("POST", _ctx("admin")), view
    )


def test_api_key_viewset_declares_governance_scope_for_mutations() -> None:
    """Key management is ADMIN-tier for API keys, READ-tier for roles (#716)."""
    view = ApiKeyViewSet()
    assert ApiKeyViewSet.required_operation is Operation.READ  # unchanged (#716)

    view.request = SimpleNamespace(method="POST")
    assert view.required_scope_operation is Operation.ASSIGN_ROLE
    view.request = SimpleNamespace(method="DELETE")
    assert view.required_scope_operation is Operation.ASSIGN_ROLE

    view.request = SimpleNamespace(method="GET")
    assert view.required_scope_operation is None


def test_api_key_viewset_without_request_fails_closed_to_reads_only() -> None:
    """``getattr(self, 'request', None)`` guard: no request -> no added gate."""
    assert ApiKeyViewSet().required_scope_operation is None


def test_author_key_cannot_post_to_api_key_viewset() -> None:
    """The real ViewSet through the real permission class (privilege escalation)."""
    view = ApiKeyViewSet()
    view.request = SimpleNamespace(method="POST")
    with pytest.raises(exceptions.PermissionDenied):
        RbacPermission().has_permission(_request("POST", _ctx("author")), view)


# ---------------------------------------------------------------------------
# HasOperationPermission — author tier on the ~25 views using that class
# ---------------------------------------------------------------------------


def test_has_operation_permission_author_denied_on_governance_view() -> None:
    with pytest.raises(exceptions.PermissionDenied):
        HasOperationPermission().has_permission(
            _request("PUT", _ctx("author")), _governance_view()
        )


def test_has_operation_permission_author_allowed_on_content_write() -> None:
    view = _View()
    view.required_operation = Operation.WRITE
    assert HasOperationPermission().has_permission(_request("POST", _ctx("author")), view)


def test_has_operation_permission_legacy_write_unchanged() -> None:
    assert HasOperationPermission().has_permission(
        _request("PUT", _ctx("write")), _governance_view()
    )


# ---------------------------------------------------------------------------
# Baseline gate override/waiver — the governance choke point (REST + MCP)
# ---------------------------------------------------------------------------


def test_baseline_override_denied_for_author_scope() -> None:
    with pytest.raises(PermissionDeniedError) as exc:
        BaselineFacade._assert_override_permission(_ctx("author"))
    assert "governance" in str(exc.value)


def test_baseline_override_denied_for_read_only_scope() -> None:
    with pytest.raises(PermissionDeniedError):
        BaselineFacade._assert_override_permission(_ctx("read"))


@pytest.mark.parametrize("scope", ["admin", "write"])
def test_baseline_override_allowed_for_admin_tier(scope: str) -> None:
    BaselineFacade._assert_override_permission(_ctx(scope))


def test_baseline_override_still_denied_without_approval_role() -> None:
    """The role check is unchanged — the scope tier only narrows it further."""
    with pytest.raises(PermissionDeniedError):
        BaselineFacade._assert_override_permission(_ctx("admin", roles=(ROLE_EDITOR,)))


# ---------------------------------------------------------------------------
# End-to-end: real requests, real API keys of every tier
# ---------------------------------------------------------------------------

_NEEDS_CREATE = "/api/v1/workspaces/{ws}/needs/"
_NEEDS_LIST = "/api/v1/workspaces/{ws}/needs/"
_KEYS_CREATE = "/api/v1/api-keys/"


@pytest.fixture
def ws_context(db):
    tenant = Tenant.objects.create(
        name="AKS-T", slug=f"aks-t-{uuid.uuid4().hex[:8]}", is_active=True
    )
    set_request_tenant(tenant.id)
    try:
        user = User.objects.create(
            username=f"aks-{uuid.uuid4().hex[:8]}", email="aks@t.test", tenant=tenant
        )
        workspace = Workspace.objects.create(
            tenant=tenant, name="AKS-WS", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    return tenant, user, workspace


def _api_key_client(tenant: Tenant, user: User, scope: str) -> APIClient:
    result = AuthenticationService().create_api_key(
        user_id=user.id, tenant_id=tenant.id, name=f"key-{scope}", scope=scope
    )
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=result.plaintext)
    return client


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("scope", "write_status", "key_mgmt_status"),
    [
        # NEW tiers (#865)
        ("read_only", 403, 403),
        ("author", 201, 403),
        ("admin", 201, 201),
        # LEGACY values: unchanged behaviour, including key management.
        ("read", 403, 403),
        ("write", 201, 201),
    ],
)
def test_end_to_end_scope_matrix(ws_context, scope, write_status, key_mgmt_status) -> None:
    """READ_ONLY never writes, AUTHOR writes content but not governance."""
    tenant, user, workspace = ws_context
    client = _api_key_client(tenant, user, scope)

    write = client.post(
        _NEEDS_CREATE.format(ws=workspace.id), {"title": f"need-{scope}"}, format="json"
    )
    assert write.status_code == write_status, write.content

    key_mgmt = client.post(_KEYS_CREATE, {"name": f"minted-{scope}"}, format="json")
    assert key_mgmt.status_code == key_mgmt_status, key_mgmt.content


@pytest.mark.django_db
def test_author_scope_reads_still_work(ws_context) -> None:
    tenant, user, workspace = ws_context
    client = _api_key_client(tenant, user, "author")
    assert client.get(_NEEDS_LIST.format(ws=workspace.id)).status_code == 200
    assert client.get("/api/v1/api-keys/").status_code == 200


@pytest.mark.django_db
def test_author_scope_message_names_the_required_tier(ws_context) -> None:
    tenant, user, workspace = ws_context
    client = _api_key_client(tenant, user, "author")
    resp = client.post(_KEYS_CREATE, {"name": "nope"}, format="json")
    assert resp.status_code == 403
    assert "admin" in str(resp.content).lower()
