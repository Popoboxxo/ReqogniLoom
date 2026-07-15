"""
Regression tests for CSRF_TRUSTED_ORIGINS enforcement (REQ-139).

Background / root cause (REQ-138):
    The production bug caused by missing/wrong CSRF_TRUSTED_ORIGINS was never
    caught by the existing test suite because:
      1. APIRequestFactory uses enforce_csrf_checks=False by default.
      2. Playwright API calls omit the Origin header → no origin check.
      3. Playwright UI tests ran against localhost:5173 which was already in
         the default CSRF_TRUSTED_ORIGINS value in settings.py.

How CSRF is enforced in ReqFlow (DRF + custom cookie auth):
    All DRF views are @csrf_exempt (Django's CSRF middleware is bypassed).
    For *cookie-authenticated* requests the custom auth class (auth_tenancy/rest.py)
    calls ``_enforce_csrf(request)`` which runs ``CSRFCheck.process_view`` —
    a subclass of Django's ``CsrfViewMiddleware``. This is where
    CSRF_TRUSTED_ORIGINS is checked.

    Flow for a browser POST with access cookie:
      1. authenticate() finds access cookie → calls _enforce_csrf()
      2. _enforce_csrf() calls CSRFCheck.process_view()
      3. process_view() checks HTTP_ORIGIN against CSRF_TRUSTED_ORIGINS
         - If NOT trusted → raises PermissionDenied("CSRF Failed: Origin …")
           → 403 response with that message
         - If trusted → continue to CSRF token check (X-CSRFToken header)
      4. If token matches cookie → request is processed normally

    The regression in REQ-138 caused step 3 to fail for http://localhost:5173
    (the production frontend) because CSRF_TRUSTED_ORIGINS was wrong.

Endpoint under test: POST /api/v1/auth/logout/
    Same endpoint used in test_auth_cookie.py for CSRF tests. After login the
    access cookie is set; the logout POST triggers _enforce_csrf so any CSRF
    failure is visible in the response before business logic runs.
"""
from __future__ import annotations

import pytest
from django.test import override_settings

from auth_tenancy.models import ROLE_ADMIN, UserRole
from auth_tenancy.rest import ACCESS_COOKIE_NAME
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from rest_framework.test import APIClient

_SECRET = "csrf-regression-test-secret"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)

_LOGIN_URL = "/api/v1/auth/login/"
_LOGOUT_URL = "/api/v1/auth/logout/"

# Django / ReqFlow CSRF rejection substrings (from _enforce_csrf → PermissionDenied).
_REASON_BAD_ORIGIN = "does not match any trusted origins"
_REASON_NO_CSRF_COOKIE = "CSRF cookie not set"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def csrf_user(db):
    """Tenant + admin user + workspace, same pattern as test_auth_cookie.py."""
    tenant = Tenant.objects.create(
        name="CSRF Regression Tenant", slug="csrf-regr", is_active=True
    )
    user = User.objects.create(
        username="csrfregr", email="csrfregr@t.test", tenant=tenant
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


def _login(client: APIClient) -> None:
    """Log in ``csrfregr`` — sets the httpOnly access cookie and csrftoken cookie."""
    resp = client.post(
        _LOGIN_URL,
        {"username": "csrfregr", "password": "hunter2pass"},
        format="json",
    )
    assert resp.status_code == 200, f"Login failed: {resp.content!r}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@override_settings(
    DEBUG=True,
    CSRF_TRUSTED_ORIGINS=["http://localhost:5173"],
    **_JWT_OVERRIDES,
)
@pytest.mark.django_db
def test_req139_cookie_post_with_untrusted_origin_is_csrf_blocked(csrf_user):
    """[REQ-139] Cookie-authenticated POST from untrusted origin → 403 CSRF Failed."""
    client = APIClient(enforce_csrf_checks=True)
    _login(client)
    csrf_token = client.cookies["csrftoken"].value

    resp = client.post(
        _LOGOUT_URL,
        {},
        format="json",
        # Trusted origin (for CSRF token acceptance) but the *Origin header*
        # is from an untrusted domain — this triggers REASON_BAD_ORIGIN.
        HTTP_ORIGIN="http://evil.example.com",
        HTTP_X_CSRFTOKEN=csrf_token,
    )

    assert resp.status_code == 403, (
        f"Expected 403 for untrusted origin, got {resp.status_code}. "
        f"Body: {resp.content!r}"
    )
    assert _REASON_BAD_ORIGIN in resp.content.decode(), (
        f"Expected bad-origin CSRF message in response body, got: {resp.content!r}"
    )


@override_settings(
    DEBUG=True,
    CSRF_TRUSTED_ORIGINS=["http://localhost:5173"],
    **_JWT_OVERRIDES,
)
@pytest.mark.django_db
def test_req139_cookie_post_with_trusted_origin_is_not_csrf_blocked(csrf_user):
    """[REQ-139] Cookie-authenticated POST from trusted origin + CSRF token → not 403."""
    client = APIClient(enforce_csrf_checks=True)
    _login(client)
    csrf_token = client.cookies["csrftoken"].value

    resp = client.post(
        _LOGOUT_URL,
        {},
        format="json",
        HTTP_ORIGIN="http://localhost:5173",  # listed in CSRF_TRUSTED_ORIGINS
        HTTP_X_CSRFTOKEN=csrf_token,
    )

    assert resp.status_code != 403, (
        f"CSRF middleware blocked a POST from a trusted origin with 403. "
        f"CSRF_TRUSTED_ORIGINS is likely misconfigured. Body: {resp.content!r}"
    )
    assert _REASON_BAD_ORIGIN not in resp.content.decode(), (
        f"Response contains bad-origin CSRF message for a trusted origin: {resp.content!r}"
    )
    # Logout returns 204 on success; any non-403 is acceptable here.
    assert resp.status_code in (200, 204, 401, 405), (
        f"Unexpected status code {resp.status_code}. Body: {resp.content!r}"
    )
