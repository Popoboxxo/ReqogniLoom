"""
Tests for ItemPermissionViewSet REST endpoints (REQ-L1-039).

Covers the Welle C REST adapter:

* POST /api/v1/workspaces/{ws}/permissions/  — grant
* GET  /api/v1/workspaces/{ws}/permissions/  — list
* DELETE /api/v1/workspaces/{ws}/permissions/ — revoke
* Error mapping: 400 / 403 / 404
* Auth context wiring and admin gate at the service layer

Tests follow the same pattern as ``test_api_key_rest.py``: the view is
constructed directly with a mocked auth context, the service is patched
where useful, and the responses are asserted without spinning up the full
DRF stack. A couple of DB-backed integration tests exercise the full
``request -> view -> service -> DB`` path.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from rest_framework import status
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import (
    ITEM_PERMISSION_READ,
    ITEM_PERMISSION_WRITE,
    ItemPermission,
)
from auth_tenancy.services import ItemPermissionService

from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

from .conftest import active_tenant


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOCK_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
_MOCK_TENANT_ID = UUID("00000000-0000-0000-0000-000000000002")
_MOCK_API_KEY_ID = UUID("00000000-0000-0000-0000-000000000003")

_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000010")
_OTHER_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000011")
_TARGET_USER_ID = UUID("00000000-0000-0000-0000-000000000020")
_ARTIFACT_ID = UUID("00000000-0000-0000-0000-000000000030")


def _admin_ctx() -> AuthContext:
    return AuthContext(
        user_id=_MOCK_USER_ID,
        tenant_id=_MOCK_TENANT_ID,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
        api_key_id=_MOCK_API_KEY_ID,
    )


def _make_request(
    method: str,
    url: str,
    *,
    body=None,
    auth: AuthContext | None = None,
):
    """Build a DRF Request and attach parser_context for URL kwargs.

    The view is a DRF APIView, so it expects ``request.data`` and
    ``request.query_params`` (the DRF ``Request`` interface). We wrap the
    raw WSGI request with ``rest_framework.request.Request`` and wire a
    minimal ``parser_context``.
    """
    factory = APIRequestFactory()
    if method == "GET":
        raw = factory.get(url)
    elif method == "POST":
        raw = factory.post(url, data=body or {}, format="json")
    elif method == "DELETE":
        raw = factory.delete(url, data=body or {}, format="json")
    else:  # pragma: no cover
        raise ValueError(method)
    # Wrap in DRF's Request so .data and .query_params are available.
    request = Request(raw, parsers=[rest_framework_json_parser()])
    request.auth_context = auth
    # APIView uses request.parser_context to expose URL kwargs; build a
    # minimal one for the tests.
    request.parser_context = {
        "kwargs": {"workspace_id": str(_WORKSPACE_ID)},
        "args": (),
        "view": None,
    }
    return request


def rest_framework_json_parser():
    from rest_framework.parsers import JSONParser

    return JSONParser()


def _mock_permission(*, level: str = ITEM_PERMISSION_READ) -> MagicMock:
    p = MagicMock()
    p.id = uuid.uuid4()
    p.user_id = _TARGET_USER_ID
    p.workspace_id = _WORKSPACE_ID
    p.artifact_id = None
    p.permission_level = level
    p.granted_by_id = _MOCK_USER_ID
    p.is_workspace_wide = True
    p.is_explicit_deny = False
    return p


# ---------------------------------------------------------------------------
# Tests — POST (grant)
# ---------------------------------------------------------------------------


class TestItemPermissionGrant:
    """POST /api/v1/workspaces/{ws}/permissions/"""

    @patch("auth_tenancy.rest_item_permission.ItemPermissionService")
    def test_grant_returns_201_with_serialised_permission(self, mock_cls):
        mock_svc = mock_cls.return_value
        perm = _mock_permission(level=ITEM_PERMISSION_READ)
        mock_svc.grant_permission.return_value = perm

        from auth_tenancy.rest_item_permission import ItemPermissionViewSet

        view = ItemPermissionViewSet()
        view._service = mock_svc
        request = _make_request(
            "POST",
            f"/api/v1/workspaces/{_WORKSPACE_ID}/permissions/",
            body={
                "user_id": str(_TARGET_USER_ID),
                "permission_level": "read",
            },
            auth=_admin_ctx(),
        )
        response = view.post(request)

        assert response.status_code == status.HTTP_201_CREATED
        body = response.data
        assert body["permission"]["permission_level"] == ITEM_PERMISSION_READ
        assert body["permission"]["user_id"] == str(_TARGET_USER_ID)
        assert body["permission"]["workspace_id"] == str(_WORKSPACE_ID)
        mock_svc.grant_permission.assert_called_once()

    @patch("auth_tenancy.rest_item_permission.ItemPermissionService")
    def test_grant_with_artifact_id(self, mock_cls):
        mock_svc = mock_cls.return_value
        perm = _mock_permission(level=ITEM_PERMISSION_WRITE)
        perm.artifact_id = _ARTIFACT_ID
        perm.is_workspace_wide = False
        mock_svc.grant_permission.return_value = perm

        from auth_tenancy.rest_item_permission import ItemPermissionViewSet

        view = ItemPermissionViewSet()
        view._service = mock_svc
        request = _make_request(
            "POST",
            f"/api/v1/workspaces/{_WORKSPACE_ID}/permissions/",
            body={
                "user_id": str(_TARGET_USER_ID),
                "artifact_id": str(_ARTIFACT_ID),
                "permission_level": "write",
            },
            auth=_admin_ctx(),
        )
        response = view.post(request)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["permission"]["artifact_id"] == str(_ARTIFACT_ID)
        assert response.data["permission"]["is_workspace_wide"] is False

    @patch("auth_tenancy.rest_item_permission.ItemPermissionService")
    def test_grant_missing_user_id_returns_400(self, mock_cls):
        from auth_tenancy.rest_item_permission import ItemPermissionViewSet

        view = ItemPermissionViewSet()
        view._service = mock_cls.return_value
        request = _make_request(
            "POST",
            f"/api/v1/workspaces/{_WORKSPACE_ID}/permissions/",
            body={"permission_level": "read"},
            auth=_admin_ctx(),
        )
        response = view.post(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "VALIDATION_ERROR"

    @patch("auth_tenancy.rest_item_permission.ItemPermissionService")
    def test_grant_invalid_level_returns_400(self, mock_cls):
        from auth_tenancy.rest_item_permission import ItemPermissionViewSet

        view = ItemPermissionViewSet()
        view._service = mock_cls.return_value
        request = _make_request(
            "POST",
            f"/api/v1/workspaces/{_WORKSPACE_ID}/permissions/",
            body={
                "user_id": str(_TARGET_USER_ID),
                "permission_level": "superuser",
            },
            auth=_admin_ctx(),
        )
        response = view.post(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "VALIDATION_ERROR"

    @patch("auth_tenancy.rest_item_permission.ItemPermissionService")
    def test_grant_invalid_uuid_returns_400(self, mock_cls):
        from auth_tenancy.rest_item_permission import ItemPermissionViewSet

        view = ItemPermissionViewSet()
        view._service = mock_cls.return_value
        request = _make_request(
            "POST",
            f"/api/v1/workspaces/{_WORKSPACE_ID}/permissions/",
            body={"user_id": "not-a-uuid", "permission_level": "read"},
            auth=_admin_ctx(),
        )
        response = view.post(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("auth_tenancy.rest_item_permission.ItemPermissionService")
    def test_grant_non_admin_returns_403(self, mock_cls):
        mock_svc = mock_cls.return_value
        mock_svc.grant_permission.side_effect = PermissionDeniedError(
            "Permission denied: role 'admin' required"
        )

        from auth_tenancy.rest_item_permission import ItemPermissionViewSet

        view = ItemPermissionViewSet()
        view._service = mock_svc
        ctx = AuthContext(
            user_id=_MOCK_USER_ID,
            tenant_id=_MOCK_TENANT_ID,
            active_roles=("editor",),
            auth_method=AuthMethod.BEARER_TOKEN,
        )
        request = _make_request(
            "POST",
            f"/api/v1/workspaces/{_WORKSPACE_ID}/permissions/",
            body={
                "user_id": str(_TARGET_USER_ID),
                "permission_level": "read",
            },
            auth=ctx,
        )
        response = view.post(request)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.data["error"] == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# Tests — GET (list)
# ---------------------------------------------------------------------------


class TestItemPermissionList:
    """GET /api/v1/workspaces/{ws}/permissions/"""

    @patch("auth_tenancy.rest_item_permission.ItemPermissionService")
    def test_list_returns_200_with_rules(self, mock_cls):
        mock_svc = mock_cls.return_value
        p1 = _mock_permission(level=ITEM_PERMISSION_READ)
        p2 = _mock_permission(level=ITEM_PERMISSION_WRITE)
        p2.artifact_id = _ARTIFACT_ID
        p2.is_workspace_wide = False
        mock_svc.list_permissions.return_value = [p1, p2]

        from auth_tenancy.rest_item_permission import ItemPermissionViewSet

        view = ItemPermissionViewSet()
        view._service = mock_svc
        request = _make_request(
            "GET",
            f"/api/v1/workspaces/{_WORKSPACE_ID}/permissions/?user_id={_TARGET_USER_ID}",
            auth=_admin_ctx(),
        )
        response = view.get(request)

        assert response.status_code == status.HTTP_200_OK
        body = response.data
        assert "permissions" in body
        assert len(body["permissions"]) == 2

    @patch("auth_tenancy.rest_item_permission.ItemPermissionService")
    def test_list_missing_user_id_returns_400(self, mock_cls):
        from auth_tenancy.rest_item_permission import ItemPermissionViewSet

        view = ItemPermissionViewSet()
        view._service = mock_cls.return_value
        request = _make_request(
            "GET",
            f"/api/v1/workspaces/{_WORKSPACE_ID}/permissions/",
            auth=_admin_ctx(),
        )
        response = view.get(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("auth_tenancy.rest_item_permission.ItemPermissionService")
    def test_list_with_artifact_filter(self, mock_cls):
        mock_svc = mock_cls.return_value
        p1 = _mock_permission(level=ITEM_PERMISSION_READ)
        p1.is_workspace_wide = True
        p2 = _mock_permission(level=ITEM_PERMISSION_WRITE)
        p2.artifact_id = _ARTIFACT_ID
        p2.is_workspace_wide = False
        mock_svc.list_permissions.return_value = [p1, p2]

        from auth_tenancy.rest_item_permission import ItemPermissionViewSet

        view = ItemPermissionViewSet()
        view._service = mock_svc
        request = _make_request(
            "GET",
            (
                f"/api/v1/workspaces/{_WORKSPACE_ID}/permissions/"
                f"?user_id={_TARGET_USER_ID}&artifact_id={_ARTIFACT_ID}"
            ),
            auth=_admin_ctx(),
        )
        response = view.get(request)

        assert response.status_code == status.HTTP_200_OK
        # The post-fetch filter narrows to the artifact-scoped rule.
        assert len(response.data["permissions"]) == 1
        assert response.data["permissions"][0]["artifact_id"] == str(_ARTIFACT_ID)

    @patch("auth_tenancy.rest_item_permission.ItemPermissionService")
    def test_list_non_admin_returns_403(self, mock_cls):
        mock_svc = mock_cls.return_value
        mock_svc.list_permissions.side_effect = PermissionDeniedError(
            "Permission denied"
        )

        from auth_tenancy.rest_item_permission import ItemPermissionViewSet

        view = ItemPermissionViewSet()
        view._service = mock_svc
        ctx = AuthContext(
            user_id=_MOCK_USER_ID,
            tenant_id=_MOCK_TENANT_ID,
            active_roles=("viewer",),
            auth_method=AuthMethod.BEARER_TOKEN,
        )
        request = _make_request(
            "GET",
            f"/api/v1/workspaces/{_WORKSPACE_ID}/permissions/?user_id={_TARGET_USER_ID}",
            auth=ctx,
        )
        response = view.get(request)

        assert response.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# Tests — DELETE (revoke)
# ---------------------------------------------------------------------------


class TestItemPermissionRevoke:
    """DELETE /api/v1/workspaces/{ws}/permissions/"""

    @patch("auth_tenancy.rest_item_permission.ItemPermissionService")
    def test_revoke_returns_204(self, mock_cls):
        mock_svc = mock_cls.return_value
        mock_svc.revoke_permission.return_value = True
        perm = _mock_permission(level=ITEM_PERMISSION_READ)
        with patch(
            "auth_tenancy.rest_item_permission.ItemPermission.unscoped"
        ) as mock_unscoped:
            mock_qs = MagicMock()
            mock_unscoped.filter.return_value = mock_qs
            mock_qs.first.return_value = perm

            from auth_tenancy.rest_item_permission import ItemPermissionViewSet

            view = ItemPermissionViewSet()
            view._service = mock_svc
            request = _make_request(
                "DELETE",
                f"/api/v1/workspaces/{_WORKSPACE_ID}/permissions/",
                body={"permission_id": str(perm.id)},
                auth=_admin_ctx(),
            )
            response = view.delete(request)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_svc.revoke_permission.assert_called_once()

    @patch("auth_tenancy.rest_item_permission.ItemPermissionService")
    def test_revoke_missing_permission_id_returns_400(self, mock_cls):
        from auth_tenancy.rest_item_permission import ItemPermissionViewSet

        view = ItemPermissionViewSet()
        view._service = mock_cls.return_value
        request = _make_request(
            "DELETE",
            f"/api/v1/workspaces/{_WORKSPACE_ID}/permissions/",
            auth=_admin_ctx(),
        )
        response = view.delete(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("auth_tenancy.rest_item_permission.ItemPermissionService")
    def test_revoke_unknown_id_returns_404(self, mock_cls):
        with patch(
            "auth_tenancy.rest_item_permission.ItemPermission.unscoped"
        ) as mock_unscoped:
            mock_qs = MagicMock()
            # manager.filter(...) returns a QuerySet; QuerySet.first() returns the row or None
            mock_unscoped.filter.return_value = mock_qs
            mock_qs.first.return_value = None

            from auth_tenancy.rest_item_permission import ItemPermissionViewSet

            view = ItemPermissionViewSet()
            view._service = mock_cls.return_value
            request = _make_request(
                "DELETE",
                f"/api/v1/workspaces/{_WORKSPACE_ID}/permissions/",
                body={"permission_id": str(uuid.uuid4())},
                auth=_admin_ctx(),
            )
            response = view.delete(request)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch("auth_tenancy.rest_item_permission.ItemPermissionService")
    def test_revoke_non_admin_returns_403(self, mock_cls):
        mock_svc = mock_cls.return_value
        mock_svc.revoke_permission.side_effect = PermissionDeniedError(
            "Permission denied"
        )
        perm = _mock_permission(level=ITEM_PERMISSION_READ)
        with patch(
            "auth_tenancy.rest_item_permission.ItemPermission.unscoped"
        ) as mock_unscoped:
            mock_qs = MagicMock()
            mock_unscoped.filter.return_value = mock_qs
            mock_qs.first.return_value = perm

            from auth_tenancy.rest_item_permission import ItemPermissionViewSet

            view = ItemPermissionViewSet()
            view._service = mock_svc
            ctx = AuthContext(
                user_id=_MOCK_USER_ID,
                tenant_id=_MOCK_TENANT_ID,
                active_roles=("editor",),
                auth_method=AuthMethod.BEARER_TOKEN,
            )
            request = _make_request(
                "DELETE",
                f"/api/v1/workspaces/{_WORKSPACE_ID}/permissions/",
                body={"permission_id": str(perm.id)},
                auth=ctx,
            )
            response = view.delete(request)

        assert response.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# Integration tests — DB-backed, real service
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_rest_grant_then_list_then_revoke_integration(
    tenant_a, user_a, workspace_a
):
    """End-to-end POST -> GET -> DELETE on the REST view (no DRF runner)."""
    from auth_tenancy.rest_item_permission import ItemPermissionViewSet
    from persistence.models import Artifact, User

    with active_tenant(tenant_a):
        subject = User.objects.create(
            username="bob", email="bob@a.test", tenant=tenant_a
        )
        # service call to set up
        ItemPermissionService().grant_permission(
            AuthContext(
                user_id=user_a.id,
                tenant_id=tenant_a.id,
                active_roles=("admin",),
                auth_method=AuthMethod.BEARER_TOKEN,
            ),
            user_id=subject.id,
            workspace_id=workspace_a.id,
            artifact_id=None,
            level=ITEM_PERMISSION_READ,
            granted_by_user_id=user_a.id,
        )
        created_perm = ItemPermission.objects.filter(
            user_id=subject.id, workspace_id=workspace_a.id
        ).get()

    admin_ctx = AuthContext(
        user_id=user_a.id,
        tenant_id=tenant_a.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )

    view = ItemPermissionViewSet()

    # List — should return the rule we just created via the service.
    list_req = _make_request(
        "GET",
        f"/api/v1/workspaces/{workspace_a.id}/permissions/?user_id={subject.id}",
        auth=admin_ctx,
    )
    list_req.parser_context["kwargs"]["workspace_id"] = str(workspace_a.id)
    list_resp = view.get(list_req)
    assert list_resp.status_code == status.HTTP_200_OK
    assert len(list_resp.data["permissions"]) == 1
    assert list_resp.data["permissions"][0]["permission_level"] == ITEM_PERMISSION_READ

    # Revoke.
    with active_tenant(tenant_a):
        assert ItemPermission.objects.filter(id=created_perm.id).exists()
    delete_req = _make_request(
        "DELETE",
        f"/api/v1/workspaces/{workspace_a.id}/permissions/",
        body={"permission_id": str(created_perm.id)},
        auth=admin_ctx,
    )
    delete_req.parser_context["kwargs"]["workspace_id"] = str(workspace_a.id)
    delete_resp = view.delete(delete_req)
    assert delete_resp.status_code == status.HTTP_204_NO_CONTENT

    # Row is gone.
    with active_tenant(tenant_a):
        assert not ItemPermission.objects.filter(id=created_perm.id).exists()
