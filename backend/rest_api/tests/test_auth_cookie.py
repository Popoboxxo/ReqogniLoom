"""
ARCH-L1-002 RestApiAdapter — httpOnly access-cookie + CSRF tests (REQ-052).

Covers the XSS-hardening auth flow that moves the JWT out of JavaScript reach:

* login sets an ``HttpOnly; SameSite=Lax; Path=/api`` access cookie (and still
  returns the body token for Phase-1 backward compatibility),
* the cookie alone authenticates a follow-up request (dual-read fallback); an
  invalid cookie is rejected,
* cookie-authenticated *unsafe* methods require an ``X-CSRFToken`` (403 without,
  2xx with), while header/Bearer auth stays CSRF-exempt,
* logout clears the cookie (``Max-Age=0``).

CSRF is only enforced when the DRF test client runs with
``enforce_csrf_checks=True`` (mirrors a real browser); the default client keeps
the existing header-based tests green.
"""
from __future__ import annotations

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from auth_tenancy.rest import ACCESS_COOKIE_NAME
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

_SECRET = "test-secret-not-a-real-key"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


@pytest.fixture
def admin_user(db):
    """An active admin user with a password and an admin UserRole."""
    tenant = Tenant.objects.create(name="Cookie T", slug="cookie-t", is_active=True)
    user = User.objects.create(
        username="cookieadmin", email="cookieadmin@t.test", tenant=tenant
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
    """Log in ``cookieadmin`` and return the raw login response."""
    return client.post(
        "/api/v1/auth/login/",
        {"username": "cookieadmin", "password": "hunter2pass"},
        format="json",
    )


# ---------------------------------------------------------------------------
# Cookie issuance
# ---------------------------------------------------------------------------


@override_settings(DEBUG=True, AUTH_COOKIE_SECURE=False, **_JWT_OVERRIDES)
@pytest.mark.django_db
def test_login_sets_httponly_access_cookie(admin_user):
    """Login response carries an HttpOnly; SameSite=Lax; Path=/api cookie."""
    client = APIClient()
    resp = _login(client)

    assert resp.status_code == 200
    # Body token still present (Phase-1 backward compatibility).
    assert resp.json()["token"]

    cookie = resp.cookies[ACCESS_COOKIE_NAME]
    assert cookie.value  # the JWT
    assert cookie["httponly"] is True
    assert cookie["samesite"] == "Lax"
    assert cookie["path"] == "/api"
    # AUTH_COOKIE_SECURE=False → Secure omitted so local HTTP works.
    assert cookie["secure"] == ""


@override_settings(
    DEBUG=False,
    AUTH_COOKIE_SECURE=True,
    ALLOWED_HOSTS=["testserver"],
    **_JWT_OVERRIDES,
)
@pytest.mark.django_db
def test_login_cookie_is_secure_when_not_debug(admin_user):
    """With AUTH_COOKIE_SECURE=True the access cookie is marked Secure (HTTPS-only).

    AUTH_COOKIE_SECURE defaults to ``not DEBUG`` but is resolved once at
    settings-load time, so the test overrides it explicitly rather than
    relying on ``override_settings(DEBUG=...)`` alone (REQ-052/REQ-115).
    """
    client = APIClient()
    resp = _login(client)
    assert resp.cookies[ACCESS_COOKIE_NAME]["secure"] is True


@override_settings(
    DEBUG=False,
    AUTH_COOKIE_SECURE=False,
    ALLOWED_HOSTS=["testserver"],
    **_JWT_OVERRIDES,
)
@pytest.mark.django_db
def test_login_cookie_secure_follows_dedicated_setting_not_debug(admin_user):
    """AUTH_COOKIE_SECURE=False omits Secure even with DEBUG=False.

    Covers HTTP-only internal/sandbox deployments (REQ-115) that must run
    with DEBUG=False but have no TLS termination in front of them.
    """
    client = APIClient()
    resp = _login(client)
    assert resp.cookies[ACCESS_COOKIE_NAME]["secure"] == ""


# ---------------------------------------------------------------------------
# Dual-read: cookie authenticates without an Authorization header
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_cookie_only_authenticates_safe_request(admin_user):
    """A GET carrying only the access cookie (no header) resolves to 200."""
    client = APIClient()
    token = _login(client).json()["token"]

    cookie_client = APIClient()
    cookie_client.cookies[ACCESS_COOKIE_NAME] = token
    resp = cookie_client.get("/api/v1/auth/me/")

    assert resp.status_code == 200
    assert resp.json()["user"]["username"] == "cookieadmin"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_invalid_cookie_is_rejected(admin_user):
    """A malformed access cookie yields 401 (present-but-invalid credential)."""
    client = APIClient()
    client.cookies[ACCESS_COOKIE_NAME] = "not-a-valid-jwt"
    resp = client.get("/api/v1/auth/me/")
    assert resp.status_code == 401


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_header_bearer_still_works(admin_user):
    """Regression: header Bearer auth is unaffected by the dual-read change."""
    client = APIClient()
    token = _login(client).json()["token"]

    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    resp = authed.get("/api/v1/auth/me/")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# CSRF enforcement on the cookie path (unsafe methods)
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_cookie_post_without_csrf_is_forbidden(admin_user):
    """Cookie-authenticated POST without X-CSRFToken is rejected (403)."""
    client = APIClient(enforce_csrf_checks=True)
    _login(client)  # sets both the access cookie and the csrftoken cookie

    resp = client.post("/api/v1/auth/logout/", {}, format="json")
    assert resp.status_code == 403


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_cookie_post_with_csrf_succeeds(admin_user):
    """Cookie-authenticated POST with a matching X-CSRFToken passes (2xx)."""
    client = APIClient(enforce_csrf_checks=True)
    _login(client)
    csrf_token = client.cookies["csrftoken"].value

    resp = client.post(
        "/api/v1/auth/logout/",
        {},
        format="json",
        HTTP_X_CSRFTOKEN=csrf_token,
    )
    assert resp.status_code == 204


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_header_auth_post_skips_csrf(admin_user):
    """Header/Bearer POST stays CSRF-exempt even under strict enforcement."""
    client = APIClient()
    token = _login(client).json()["token"]

    authed = APIClient(enforce_csrf_checks=True)
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    resp = authed.post("/api/v1/auth/logout/", {}, format="json")
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Logout clears the cookie
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_logout_deletes_access_cookie(admin_user):
    """Logout response expires the access cookie (Max-Age=0)."""
    client = APIClient()
    token = _login(client).json()["token"]

    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    resp = authed.post("/api/v1/auth/logout/", {}, format="json")

    assert resp.status_code == 204
    cookie = resp.cookies[ACCESS_COOKIE_NAME]
    assert cookie["max-age"] == 0
    assert cookie["path"] == "/api"
