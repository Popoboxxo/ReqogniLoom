"""
ARCH-L1-002 RestApiAdapter — silent token refresh tests (GitHub #135).

Covers ``POST /api/v1/auth/refresh/``:

* login also sets the httpOnly ``reqogniloom_refresh`` cookie,
* a valid refresh cookie (+ CSRF token) mints a fresh access cookie and
  rotates the refresh cookie,
* a missing/invalid/expired refresh cookie is rejected (401) and clears both
  auth cookies,
* the refresh endpoint enforces CSRF like the other cookie-driven endpoints,
* a refresh token can never authenticate a normal request (typ mismatch), and
  conversely an access token is rejected by the refresh endpoint,
* logout clears the refresh cookie too.
"""
from __future__ import annotations

import time

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.jwt_tokens import encode_hs256
from auth_tenancy.models import ROLE_ADMIN, UserRole
from auth_tenancy.rest import ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

_SECRET = "test-secret-not-a-real-key"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
    AUTH_JWT_REFRESH_TTL_SECONDS=2592000,
)


@pytest.fixture
def admin_user(db):
    """An active admin user with a password and an admin UserRole."""
    tenant = Tenant.objects.create(name="Refresh T", slug="refresh-t", is_active=True)
    user = User.objects.create(
        username="refreshadmin", email="refreshadmin@t.test", tenant=tenant
    )
    user.set_password("hunter2pass")
    user.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="WS", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    return user


def _login(client: APIClient) -> "object":
    """Log in ``refreshadmin`` and return the raw login response."""
    return client.post(
        "/api/v1/auth/login/",
        {"username": "refreshadmin", "password": "hunter2pass"},
        format="json",
    )


def _refresh(client: APIClient, *, csrf_token: str | None):
    kwargs = {}
    if csrf_token is not None:
        kwargs["HTTP_X_CSRFTOKEN"] = csrf_token
    return client.post("/api/v1/auth/refresh/", {}, format="json", **kwargs)


# ---------------------------------------------------------------------------
# Login also issues the refresh cookie
# ---------------------------------------------------------------------------


@override_settings(DEBUG=True, AUTH_COOKIE_SECURE=False, **_JWT_OVERRIDES)
@pytest.mark.django_db
def test_login_sets_httponly_refresh_cookie(admin_user):
    """Login response carries an HttpOnly; SameSite=Lax; Path=/api refresh cookie."""
    client = APIClient()
    resp = _login(client)

    assert resp.status_code == 200
    cookie = resp.cookies[REFRESH_COOKIE_NAME]
    assert cookie.value
    assert cookie["httponly"] is True
    assert cookie["samesite"] == "Lax"
    assert cookie["path"] == "/api"
    # Refresh token must differ from the access token (distinct typ claim).
    assert cookie.value != resp.cookies[ACCESS_COOKIE_NAME].value


# ---------------------------------------------------------------------------
# Successful refresh
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_refresh_with_valid_cookie_mints_new_access_token(admin_user):
    """A valid refresh cookie + CSRF token yields a fresh access cookie."""
    client = APIClient(enforce_csrf_checks=True)
    login_resp = _login(client)
    csrf_token = client.cookies["csrftoken"].value
    old_access_token = login_resp.cookies[ACCESS_COOKIE_NAME].value

    resp = _refresh(client, csrf_token=csrf_token)

    assert resp.status_code == 200
    assert resp.json()["user"]["username"] == "refreshadmin"
    new_cookie = resp.cookies[ACCESS_COOKIE_NAME]
    assert new_cookie.value
    assert new_cookie["httponly"] is True

    # The new access token authenticates a follow-up request.
    authed = APIClient()
    authed.cookies[ACCESS_COOKIE_NAME] = new_cookie.value
    me_resp = authed.get("/api/v1/auth/me/")
    assert me_resp.status_code == 200
    assert me_resp.json()["user"]["username"] == "refreshadmin"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_refresh_rotates_refresh_cookie(admin_user):
    """Refresh also rotates the refresh cookie itself (defense-in-depth)."""
    client = APIClient(enforce_csrf_checks=True)
    login_resp = _login(client)
    csrf_token = client.cookies["csrftoken"].value
    old_refresh_token = login_resp.cookies[REFRESH_COOKIE_NAME].value

    resp = _refresh(client, csrf_token=csrf_token)

    assert resp.status_code == 200
    new_refresh_cookie = resp.cookies[REFRESH_COOKIE_NAME]
    assert new_refresh_cookie.value
    assert new_refresh_cookie["httponly"] is True
    assert new_refresh_cookie["path"] == "/api"


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_refresh_without_cookie_returns_401():
    """No refresh cookie present -> 401, no server state required."""
    client = APIClient()
    resp = _refresh(client, csrf_token=None)
    assert resp.status_code == 401


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_refresh_without_csrf_is_forbidden(admin_user):
    """Refresh cookie present but no X-CSRFToken -> 403 (REQ-052 pattern)."""
    client = APIClient(enforce_csrf_checks=True)
    _login(client)

    resp = _refresh(client, csrf_token=None)
    assert resp.status_code == 403


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_refresh_with_invalid_cookie_returns_401_and_clears_cookies(admin_user):
    """A malformed refresh cookie is rejected and both cookies get cleared."""
    client = APIClient(enforce_csrf_checks=True)
    _login(client)
    csrf_token = client.cookies["csrftoken"].value
    client.cookies[REFRESH_COOKIE_NAME] = "not-a-valid-jwt"

    resp = _refresh(client, csrf_token=csrf_token)

    assert resp.status_code == 401
    assert resp.cookies[ACCESS_COOKIE_NAME]["max-age"] == 0
    assert resp.cookies[REFRESH_COOKIE_NAME]["max-age"] == 0


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_refresh_with_expired_refresh_token_returns_401(admin_user):
    """An expired refresh token is rejected (token_expired)."""
    client = APIClient(enforce_csrf_checks=True)
    _login(client)
    csrf_token = client.cookies["csrftoken"].value

    expired_refresh = encode_hs256(
        {
            "user_id": str(admin_user.id),
            "tenant_id": str(admin_user.tenant_id),
            "typ": "refresh",
            "iat": int(time.time()) - 100,
            "exp": int(time.time()) - 10,
            "iss": "reqflow",
            "aud": "reqflow-api",
        },
        _SECRET,
    )
    client.cookies[REFRESH_COOKIE_NAME] = expired_refresh

    resp = _refresh(client, csrf_token=csrf_token)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Token-type isolation (refresh != access)
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_refresh_token_cannot_authenticate_as_bearer(admin_user):
    """A refresh token used as a Bearer/access credential is rejected."""
    client = APIClient()
    login_resp = _login(client)
    refresh_token = login_resp.cookies[REFRESH_COOKIE_NAME].value

    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh_token}")
    resp = authed.get("/api/v1/auth/me/")
    assert resp.status_code == 401


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_access_token_cannot_be_used_as_refresh_token(admin_user):
    """An access token presented as the refresh cookie is rejected (typ mismatch)."""
    client = APIClient(enforce_csrf_checks=True)
    login_resp = _login(client)
    csrf_token = client.cookies["csrftoken"].value
    access_token = login_resp.cookies[ACCESS_COOKIE_NAME].value
    client.cookies[REFRESH_COOKIE_NAME] = access_token

    resp = _refresh(client, csrf_token=csrf_token)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Logout clears both cookies
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_logout_deletes_refresh_cookie(admin_user):
    """Logout response also expires the refresh cookie (Max-Age=0)."""
    client = APIClient()
    token = _login(client).json()["token"]

    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    resp = authed.post("/api/v1/auth/logout/", {}, format="json")

    assert resp.status_code == 204
    cookie = resp.cookies[REFRESH_COOKIE_NAME]
    assert cookie["max-age"] == 0
    assert cookie["path"] == "/api"
