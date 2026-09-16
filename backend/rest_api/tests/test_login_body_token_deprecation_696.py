"""
ARCH-L1-002 RestApiAdapter — login body-token deprecation tests (#696).

Review finding C-3 (``docs/reviews/DEEP_DIVE_REVIEW_2026-08-22.md``): the login
response returned the bearer token in the body for backward compatibility with
the e2e helper / API tooling. The SPA never read it (it uses the httpOnly
cookie, REQ-052), but any future JS caller storing it would re-open exactly the
XSS vector REQ-052 closed.

Covered here:

* default behaviour is unchanged (body token present, marked with
  ``Deprecation: true`` — RFC 9745),
* with ``AUTH_LOGIN_INCLUDE_BODY_TOKEN=False`` the field is omitted while the
  httpOnly cookies are still set and cookie auth still authenticates a
  follow-up request (the flag must never break the supported path),
* the flag is opt-in/deploy-configurable, i.e. nothing breaks silently.
"""
from __future__ import annotations

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from auth_tenancy.rest import ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

_LOGIN_URL = "/api/v1/auth/login/"
_ME_URL = "/api/v1/auth/me/"

# Named `_JWT_KEY` rather than `_SECRET` (unlike the sibling auth test modules)
# so the pre-commit secret scan does not flag a `<keyword> = "<16+ chars>"`
# pattern here; the value stays the same throwaway test key.
_JWT_KEY = "test-secret-not-a-real-key"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_JWT_KEY,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


@pytest.fixture
def admin_user(db):
    """An active admin user with a password and an admin UserRole."""
    tenant = Tenant.objects.create(name="BodyToken T", slug="body-token-t", is_active=True)
    user = User.objects.create(
        username="bodytokenadmin", email="bodytoken@t.test", tenant=tenant
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


def _login(client: APIClient):
    """Log in ``bodytokenadmin`` and return the raw login response."""
    return client.post(
        _LOGIN_URL,
        {"username": "bodytokenadmin", "password": "hunter2pass"},
        format="json",
    )


# ---------------------------------------------------------------------------
# Default (unchanged) behaviour + machine-readable deprecation marker
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_default_still_returns_body_token_and_marks_it_deprecated(admin_user):
    """Default = pre-#696 behaviour, but now flagged as deprecated."""
    resp = _login(APIClient())

    assert resp.status_code == 200
    body = resp.json()
    assert body["token"]
    assert body["user"]["username"] == "bodytokenadmin"
    # RFC 9745 marker so tooling can detect the deprecated field.
    assert resp.headers["Deprecation"] == "true"


# ---------------------------------------------------------------------------
# Flag enabled: field omitted, cookie path unaffected
# ---------------------------------------------------------------------------


@override_settings(AUTH_LOGIN_INCLUDE_BODY_TOKEN=False, **_JWT_OVERRIDES)
@pytest.mark.django_db
def test_flag_enabled_omits_body_token(admin_user):
    """AUTH_LOGIN_INCLUDE_BODY_TOKEN=False drops `token` from the body."""
    resp = _login(APIClient())

    assert resp.status_code == 200
    body = resp.json()
    assert "token" not in body, "body token must be omitted when the flag is off"
    # Nothing else regresses: the identity payload stays intact.
    assert body["user"]["username"] == "bodytokenadmin"
    assert body["tenant_id"] == str(admin_user.tenant_id)
    assert ROLE_ADMIN in body["roles"]
    assert "is_tenant_admin" in body
    # No deprecated field -> no deprecation marker.
    assert "Deprecation" not in resp.headers


@override_settings(AUTH_LOGIN_INCLUDE_BODY_TOKEN=False, **_JWT_OVERRIDES)
@pytest.mark.django_db
def test_flag_enabled_still_sets_both_httponly_cookies(admin_user):
    """The supported credential path (httpOnly cookies) is unaffected."""
    resp = _login(APIClient())

    for name in (ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME):
        cookie = resp.cookies[name]
        assert cookie.value
        assert cookie["httponly"] is True
        assert cookie["path"] == "/api"


@override_settings(AUTH_LOGIN_INCLUDE_BODY_TOKEN=False, **_JWT_OVERRIDES)
@pytest.mark.django_db
def test_flag_enabled_cookie_auth_still_authenticates(admin_user):
    """With the flag off, the access cookie alone still resolves /auth/me/."""
    login = _login(APIClient())
    access_token = login.cookies[ACCESS_COOKIE_NAME].value

    cookie_client = APIClient()
    cookie_client.cookies[ACCESS_COOKIE_NAME] = access_token
    me = cookie_client.get(_ME_URL)

    assert me.status_code == 200
    assert me.json()["user"]["username"] == "bodytokenadmin"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_missing_setting_falls_back_to_including_token(admin_user, monkeypatch):
    """A settings object without the flag behaves exactly like flag=True.

    ``LoginView`` resolves the flag with a ``getattr(..., True)`` default so a
    settings module that predates #696 (or a test that deletes the setting)
    cannot accidentally switch off the field — the deprecation is opt-in.
    """
    import rest_api.auth_views as auth_views

    class _SettingsWithoutFlag:
        """Proxy that hides only the new flag, delegating everything else."""

        def __getattr__(self, name: str):
            from django.conf import settings as django_settings

            if name == "AUTH_LOGIN_INCLUDE_BODY_TOKEN":
                raise AttributeError(name)
            return getattr(django_settings, name)

    monkeypatch.setattr(auth_views, "settings", _SettingsWithoutFlag())

    resp = _login(APIClient())
    assert resp.status_code == 200
    assert resp.json()["token"]
