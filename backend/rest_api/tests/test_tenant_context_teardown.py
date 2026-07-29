"""
Regression test for issue #104 — tenant-context leak across requests.

Root-cause: ``auth_tenancy.middleware.AuthTenancyMiddleware`` was implemented
but never registered in ``settings.MIDDLEWARE``, so the ``finally``-guarded
teardown (``clear_request_tenant``) never ran. ``TenantContext.tenant_id``
(thread-local) and the Postgres session variable ``app.current_tenant`` stayed
active on the worker thread after an authenticated request, leaking into the
next unauthenticated code path on the same thread.

Fix: register the middleware in ``MIDDLEWARE`` (reqogniloom/settings.py).

leaf_id : ARCH-L1-011 AuthAndTenancy (AuthTenancyMiddleware)
req_id  : REQ-L3-AT003-004
"""
from __future__ import annotations

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_VIEWER, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from persistence.tenancy import TenantContext, TenantContextNotSetError

_SECRET = "test-secret-not-a-real-key"
_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


@pytest.fixture
def authed_user(db) -> User:
    tenant = Tenant.objects.create(name="Teardown T", slug="teardown-t", is_active=True)
    user = User.objects.create(
        username="teardownuser", email="teardown@t.test", tenant=tenant
    )
    user.set_password("hunter2pass")
    user.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="WS Teardown", preset={"name": "standard"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_VIEWER
        )
    finally:
        clear_request_tenant()
    user.workspace_id = workspace.id
    return user


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_tenant_context_cleared_after_authenticated_request(authed_user):
    """Request A activates a tenant; the context MUST NOT survive the request."""
    client = APIClient()
    login_resp = client.post(
        "/api/v1/auth/login/",
        {"username": "teardownuser", "password": "hunter2pass"},
        format="json",
    )
    assert login_resp.status_code == 200, login_resp.json()
    bearer_token = login_resp.json()["token"]

    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {bearer_token}")
    resp = authed.get(
        "/api/v1/requirements/", {"workspace_id": str(authed_user.workspace_id)}
    )
    assert resp.status_code == 200, resp.json()

    # Request A is fully done — teardown must have run. A subsequent
    # unauthenticated code path on this thread (Request B) must not inherit it.
    with pytest.raises(TenantContextNotSetError):
        TenantContext.get_tenant()
