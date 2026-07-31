"""
ARCH-L1-002 RestApiAdapter — password login endpoint tests (REQ-L1-010).

End-to-end HTTP coverage for ``POST /api/v1/auth/login/`` and ``GET
/api/v1/auth/me/``:
- login success returns a token AND that token authenticates a follow-up request
  through the real ``BearerTokenAuthentication`` (full round-trip),
- wrong password -> 401 with the standardised auth-error body,
- inactive user -> 401,
- missing fields -> 401,
- ``/auth/me/`` requires a valid Bearer token.
"""
from __future__ import annotations

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
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
    tenant = Tenant.objects.create(name="Login T", slug="login-t", is_active=True)
    user = User.objects.create(
        username="loginadmin", email="loginadmin@t.test", tenant=tenant
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


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_login_success_returns_token_and_user(admin_user):
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": "loginadmin", "password": "hunter2pass"},
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token"]
    assert body["user"]["username"] == "loginadmin"
    assert body["tenant_id"] == str(admin_user.tenant_id)
    assert ROLE_ADMIN in body["roles"]


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_login_token_authenticates_follow_up_request(admin_user):
    """The login token round-trips through BearerTokenAuthentication on /auth/me/."""
    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": "loginadmin", "password": "hunter2pass"},
        format="json",
    )
    token = login.json()["token"]

    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    me = authed.get("/api/v1/auth/me/")
    assert me.status_code == 200
    body = me.json()
    assert body["user"]["username"] == "loginadmin"
    assert body["tenant_id"] == str(admin_user.tenant_id)


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_login_wrong_password_returns_401(admin_user):
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": "loginadmin", "password": "wrong"},
        format="json",
    )
    assert resp.status_code == 401
    assert "error" in resp.json()


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_login_inactive_user_returns_401(db):
    tenant = Tenant.objects.create(name="In T", slug="in-t", is_active=True)
    user = User.objects.create(
        username="inactive", email="in@t.test", tenant=tenant, is_active=False
    )
    user.set_password("pw123456")
    user.save(update_fields=["password"])

    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": "inactive", "password": "pw123456"},
        format="json",
    )
    assert resp.status_code == 401


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_me_patch_rejects_privileged_fields(admin_user):
    """PATCH /auth/me/ must not let a caller escalate roles/tenant via mass assignment.

    Regression test for SEC-002 (#69) — no privileged field may ever be
    persisted. Since QIRK-002 (#73) the endpoint additionally *rejects* such a
    payload with 400 instead of returning 200 and silently dropping the fields,
    so the no-escalation guarantee below is now enforced by refusal.
    """
    other_tenant = Tenant.objects.create(name="Other T", slug="other-t", is_active=True)

    resp = _auth_client().patch(
        "/api/v1/auth/me/",
        {
            "first_name": "Alice",
            "last_name": "Admin",
            "roles": ["superadmin"],
            "tenant_id": str(other_tenant.id),
            "is_staff": True,
            "is_superuser": True,
            "username": "hijacked",
            "email": "hijacked@evil.test",
        },
        format="json",
    )
    assert resp.status_code == 400

    # Nothing was persisted — neither the privileged fields nor the legal ones.
    admin_user.refresh_from_db()
    assert admin_user.tenant_id != other_tenant.id
    assert admin_user.is_staff is False
    assert admin_user.is_superuser is False
    assert admin_user.username == "loginadmin"
    assert admin_user.email == "loginadmin@t.test"
    assert admin_user.first_name != "Alice"

    # The identity payload still reports the original roles/tenant.
    me = _auth_client().get("/api/v1/auth/me/").json()
    assert me["tenant_id"] == str(admin_user.tenant_id)
    assert ROLE_ADMIN in me["roles"]
    assert "superadmin" not in me["roles"]


def _auth_client(username: str = "loginadmin", password: str = "hunter2pass") -> APIClient:
    """Log in and return an APIClient carrying the resulting Bearer token."""
    token = (
        APIClient()
        .post(
            "/api/v1/auth/login/",
            {"username": username, "password": password},
            format="json",
        )
        .json()["token"]
    )
    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return authed


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
@pytest.mark.parametrize(
    "field,value",
    [
        ("password", "hacked123"),
        ("is_admin", True),
        ("is_superuser", True),
        ("is_staff", True),
        ("is_active", False),
        ("roles", ["superadmin"]),
        ("tenant_id", "00000000-0000-0000-0000-000000000001"),
        ("username", "hijacked"),
        ("email", "hijacked@evil.test"),
        ("id", "00000000-0000-0000-0000-000000000002"),
    ],
)
def test_me_patch_rejects_protected_fields(admin_user, field, value):
    """QIRK-002 (#73): protected fields must be rejected with 400, not ignored.

    Previously the serializer silently dropped these and returned 200, which
    made clients believe a password change / privilege change had been applied.
    """
    resp = _auth_client().patch("/api/v1/auth/me/", {field: value}, format="json")

    assert resp.status_code == 400, f"{field} must be rejected, got {resp.status_code}"
    assert field in str(resp.json())


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_me_patch_rejects_unknown_fields(admin_user):
    """Unknown fields are rejected too, so typos surface instead of no-op'ing."""
    resp = _auth_client().patch(
        "/api/v1/auth/me/", {"frist_name": "Typo"}, format="json"
    )
    assert resp.status_code == 400
    assert "frist_name" in str(resp.json())


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_me_patch_password_does_not_change_credentials(admin_user):
    """A rejected password PATCH must leave the stored hash untouched (#73)."""
    resp = _auth_client().patch(
        "/api/v1/auth/me/", {"password": "hacked123"}, format="json"
    )
    assert resp.status_code == 400

    admin_user.refresh_from_db()
    assert admin_user.check_password("hunter2pass")
    assert not admin_user.check_password("hacked123")


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_me_patch_mixed_payload_is_rejected_atomically(admin_user):
    """A payload mixing legal and protected fields applies *nothing* (#73)."""
    resp = _auth_client().patch(
        "/api/v1/auth/me/",
        {"first_name": "Alice", "is_superuser": True},
        format="json",
    )
    assert resp.status_code == 400

    admin_user.refresh_from_db()
    assert admin_user.first_name != "Alice"
    assert admin_user.is_superuser is False


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_login_missing_fields_returns_401(db):
    client = APIClient()
    resp = client.post("/api/v1/auth/login/", {}, format="json")
    assert resp.status_code == 401


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_me_without_token_is_rejected(db):
    """No credential -> rejected. DRF returns 403 (no authenticator claims the
    request via a WWW-Authenticate header), consistent with the CRUD endpoints."""
    client = APIClient()
    resp = client.get("/api/v1/auth/me/")
    assert resp.status_code in (401, 403)


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_user_can_update_first_last_name(admin_user):
    """PATCH /auth/me/ updates first_name/last_name and persists them (REQ-006)."""
    client = APIClient()
    token = client.post(
        "/api/v1/auth/login/",
        {"username": "loginadmin", "password": "hunter2pass"},
        format="json",
    ).json()["token"]

    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    resp = authed.patch(
        "/api/v1/auth/me/",
        {"first_name": "  Ada  ", "last_name": "Lovelace"},
        format="json",
    )

    assert resp.status_code == 200
    body = resp.json()
    # Whitespace is trimmed on save.
    assert body["user"]["first_name"] == "Ada"
    assert body["user"]["last_name"] == "Lovelace"

    admin_user.refresh_from_db()
    assert admin_user.first_name == "Ada"
    assert admin_user.last_name == "Lovelace"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_user_serializer_includes_name_fields(admin_user):
    """UserProfileSerializer exposes name fields and applies partial updates."""
    from rest_api.serializers import UserProfileSerializer

    admin_user.first_name = "Grace"
    admin_user.last_name = "Hopper"
    admin_user.save(update_fields=["first_name", "last_name"])

    read = UserProfileSerializer(instance=admin_user).data
    assert read["first_name"] == "Grace"
    assert read["last_name"] == "Hopper"
    assert read["username"] == "loginadmin"

    serializer = UserProfileSerializer(
        instance=admin_user, data={"first_name": "Ada"}, partial=True
    )
    assert serializer.is_valid(), serializer.errors
    serializer.save()
    admin_user.refresh_from_db()
    # Partial update touches only first_name; last_name is preserved.
    assert admin_user.first_name == "Ada"
    assert admin_user.last_name == "Hopper"
