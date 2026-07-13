"""
Tests for WorkspaceMembersView REST endpoint (REQ-014).

Covers GET /api/v1/workspaces/{ws}/members/ — the read-only member directory
that backs the Item-Permission user picker:

* 200 with the serialised member list.
* 403 when the caller is not a workspace member (service raises PermissionDenied).
* A DB-backed integration test exercising request -> view -> service -> DB.
"""
from __future__ import annotations

from unittest.mock import patch
from uuid import UUID

import pytest
from rest_framework import status
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.errors import PermissionDenied
from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, UserRole
from auth_tenancy.services.authorization import WorkspaceMember

from .conftest import active_tenant


_MOCK_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
_MOCK_TENANT_ID = UUID("00000000-0000-0000-0000-000000000002")
_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000010")
_TARGET_USER_ID = UUID("00000000-0000-0000-0000-000000000020")


def _member_ctx(roles: tuple[str, ...] = ("admin",)) -> AuthContext:
    return AuthContext(
        user_id=_MOCK_USER_ID,
        tenant_id=_MOCK_TENANT_ID,
        active_roles=roles,
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _make_get(url: str, *, auth: AuthContext) -> Request:
    factory = APIRequestFactory()
    raw = factory.get(url)
    request = Request(raw)
    request.auth_context = auth
    request.parser_context = {
        "kwargs": {"workspace_id": str(_WORKSPACE_ID)},
        "args": (),
        "view": None,
    }
    return request


class TestWorkspaceMembersGet:
    """GET /api/v1/workspaces/{ws}/members/"""

    @patch("auth_tenancy.rest_workspace_members.AuthorizationService")
    def test_returns_200_with_members(self, mock_cls):
        mock_svc = mock_cls.return_value
        mock_svc.list_workspace_members.return_value = [
            WorkspaceMember(
                user_id=_TARGET_USER_ID,
                username="bob",
                email="bob@a.test",
                display_name="Bob Builder",
                roles=("editor", "viewer"),
            )
        ]

        from auth_tenancy.rest_workspace_members import WorkspaceMembersView

        view = WorkspaceMembersView()
        view._service = mock_svc
        request = _make_get(
            f"/api/v1/workspaces/{_WORKSPACE_ID}/members/", auth=_member_ctx()
        )
        response = view.get(request)

        assert response.status_code == status.HTTP_200_OK
        body = response.data
        assert "members" in body
        assert len(body["members"]) == 1
        member = body["members"][0]
        assert member["user_id"] == str(_TARGET_USER_ID)
        assert member["display_name"] == "Bob Builder"
        assert member["email"] == "bob@a.test"
        assert member["roles"] == ["editor", "viewer"]
        mock_svc.list_workspace_members.assert_called_once_with(
            caller_user_id=_MOCK_USER_ID, workspace_id=_WORKSPACE_ID
        )

    @patch("auth_tenancy.rest_workspace_members.AuthorizationService")
    def test_non_member_returns_403(self, mock_cls):
        mock_svc = mock_cls.return_value
        mock_svc.list_workspace_members.side_effect = PermissionDenied()

        from auth_tenancy.rest_workspace_members import WorkspaceMembersView

        view = WorkspaceMembersView()
        view._service = mock_svc
        request = _make_get(
            f"/api/v1/workspaces/{_WORKSPACE_ID}/members/",
            auth=_member_ctx(("viewer",)),
        )
        response = view.get(request)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.data["error"] == "PERMISSION_DENIED"

    @patch("auth_tenancy.rest_workspace_members.AuthorizationService")
    def test_empty_workspace_returns_200_empty_list(self, mock_cls):
        mock_svc = mock_cls.return_value
        mock_svc.list_workspace_members.return_value = []

        from auth_tenancy.rest_workspace_members import WorkspaceMembersView

        view = WorkspaceMembersView()
        view._service = mock_svc
        request = _make_get(
            f"/api/v1/workspaces/{_WORKSPACE_ID}/members/", auth=_member_ctx()
        )
        response = view.get(request)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["members"] == []


@pytest.mark.django_db
def test_rest_members_integration(tenant_a, user_a, workspace_a):
    """End-to-end GET on the REST view against real data (no DRF runner)."""
    from auth_tenancy.rest_workspace_members import WorkspaceMembersView
    from persistence.models import User

    with active_tenant(tenant_a):
        bob = User.objects.create(
            username="bob",
            email="bob@a.test",
            first_name="Bob",
            last_name="Builder",
            tenant=tenant_a,
        )
        UserRole.objects.create(
            tenant=tenant_a, user=user_a, workspace=workspace_a, role=ROLE_ADMIN
        )
        UserRole.objects.create(
            tenant=tenant_a, user=bob, workspace=workspace_a, role=ROLE_EDITOR
        )

    ctx = AuthContext(
        user_id=user_a.id,
        tenant_id=tenant_a.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )

    view = WorkspaceMembersView()
    factory = APIRequestFactory()
    raw = factory.get(f"/api/v1/workspaces/{workspace_a.id}/members/")
    request = Request(raw)
    request.auth_context = ctx
    request.parser_context = {
        "kwargs": {"workspace_id": str(workspace_a.id)},
        "args": (),
        "view": None,
    }

    with active_tenant(tenant_a):
        response = view.get(request)

    assert response.status_code == status.HTTP_200_OK
    members = response.data["members"]
    assert {m["user_id"] for m in members} == {str(user_a.id), str(bob.id)}
    bob_member = next(m for m in members if m["user_id"] == str(bob.id))
    assert bob_member["display_name"] == "Bob Builder"
    assert bob_member["roles"] == ["editor"]
