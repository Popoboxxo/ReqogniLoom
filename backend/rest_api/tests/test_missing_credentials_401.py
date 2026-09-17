"""
Regression tests for GitHub #458 — missing credentials answered 403 instead
of 401 on plain protected endpoints (``/api/v1/auth/me/``,
``/api/v1/workspaces/``).

Root cause (verified, not merely inferred):
    ``rest_framework.views.APIView.handle_exception`` downgrades a raised
    ``NotAuthenticated``/``AuthenticationFailed`` from 401 to 403 whenever
    ``get_authenticate_header()`` (which only consults ``authenticators[0]``)
    returns a falsy value. ``AuthTenancyAuthentication`` — first in
    ``DEFAULT_AUTHENTICATION_CLASSES`` — did not override
    ``authenticate_header()``, so DRF's base implementation (``None``)
    triggered the coercion for the *missing-credential* path (RbacPermission
    denies before any ``AuthError`` is raised — no exception, just
    ``has_permission() -> False``, which routes through DRF's own
    ``permission_denied()`` -> ``NotAuthenticated``).

    A present-but-invalid token was unaffected: it raises
    ``auth_tenancy.rest._StandardAuthError``, a plain ``APIException`` that is
    NOT a subclass of ``NotAuthenticated``/``AuthenticationFailed``, so the
    coercion never applied to it — hence bad-token requests already answered
    401 before this fix.

Fix: ``AuthTenancyAuthentication.authenticate_header()`` now returns
``"Bearer"``, keeping the 401 and adding a standard ``WWW-Authenticate``
header.

leaf_id : ARCH-L1-011 AuthAndTenancy / COMP-RA-003 AuthEnforcer
req_id  : REQ-L2-AT-007, REQ-L3-AT001-004, REQ-L2-RA-005, REQ-L2-RA-006
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, ROLE_VIEWER, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

_PASSWORD = "cred401pass123"


@pytest.fixture
def cred_tenant(db):
    """A tenant with an admin and a viewer user, plus a workspace."""
    tenant = Tenant.objects.create(name="Cred T", slug="cred-t", is_active=True)
    admin = User.objects.create(
        username="cred401admin", email="cred401admin@t.test", tenant=tenant
    )
    admin.set_password(_PASSWORD)
    admin.save(update_fields=["password"])
    viewer = User.objects.create(
        username="cred401viewer", email="cred401viewer@t.test", tenant=tenant
    )
    viewer.set_password(_PASSWORD)
    viewer.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="Cred WS", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        UserRole.objects.create(
            tenant=tenant, user=viewer, workspace=workspace, role=ROLE_VIEWER
        )
        yield tenant, workspace, admin, viewer
    finally:
        clear_request_tenant()


def _login(client: APIClient, username: str) -> str:
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": username, "password": _PASSWORD},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    return resp.json()["token"]


class TestMissingCredentialsReturn401:
    """No credentials at all -> 401, never 403 (GitHub #458)."""

    def test_auth_me_without_token_returns_401(self) -> None:
        resp = APIClient().get("/api/v1/auth/me/")
        assert resp.status_code == 401, resp.content

    def test_workspaces_without_token_returns_401(self) -> None:
        resp = APIClient().get("/api/v1/workspaces/")
        assert resp.status_code == 401, resp.content

    def test_missing_credentials_carries_www_authenticate_header(self) -> None:
        """DRF only adds WWW-Authenticate when an authenticator supplies one."""
        resp = APIClient().get("/api/v1/auth/me/")
        assert resp.status_code == 401
        assert resp.get("WWW-Authenticate") == "Bearer"


class TestInvalidTokenReturns401:
    """A present-but-invalid credential must still be rejected as 401."""

    def test_malformed_bearer_token_returns_401(self) -> None:
        resp = APIClient().get(
            "/api/v1/auth/me/",
            HTTP_AUTHORIZATION="Bearer kaputt.kaputt.kaputt",
        )
        assert resp.status_code == 401, resp.content

    def test_malformed_bearer_token_on_workspaces_returns_401(self) -> None:
        resp = APIClient().get(
            "/api/v1/workspaces/",
            HTTP_AUTHORIZATION="Bearer kaputt.kaputt.kaputt",
        )
        assert resp.status_code == 401, resp.content


@pytest.mark.django_db
class TestAuthenticatedButUnauthorizedStays403:
    """A real, authenticated caller without the required role stays 403.

    This is the semantic this fix must NOT change — several recent commits
    hardened exactly this boundary (admin-role enforcement fixes).
    """

    def test_non_admin_denied_write_returns_403(self, cred_tenant) -> None:
        _tenant, workspace, _admin, viewer = cred_tenant
        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {_login(client, 'cred401viewer')}"
        )

        resp = client.post(
            f"/api/v1/workspaces/{workspace.id}/needs/",
            {"title": "should be denied"},
            format="json",
        )
        assert resp.status_code == 403, resp.content

    def test_admin_allowed_write_returns_2xx(self, cred_tenant) -> None:
        _tenant, workspace, _admin, _viewer = cred_tenant
        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {_login(client, 'cred401admin')}"
        )

        resp = client.post(
            f"/api/v1/workspaces/{workspace.id}/needs/",
            {"title": "allowed for admin"},
            format="json",
        )
        assert resp.status_code in (200, 201), resp.content
