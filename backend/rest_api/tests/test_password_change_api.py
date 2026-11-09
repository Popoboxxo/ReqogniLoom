"""HTTP contract of ``POST /api/v1/auth/password/change/`` (GitHub #1739).

Drives the endpoint through the real DRF pipeline (cookie login, CSRF-exempt
APIClient, ``/auth/refresh/`` as the probe for session revocation):

* success → 204, the new password logs in, the old one does not,
* wrong current password → 400 ``INVALID_CURRENT_PASSWORD`` without echo,
* policy violation → 400 ``PASSWORD_POLICY_VIOLATION`` with a
  ``new_password`` field detail,
* the calling cookie session survives, the other login session is revoked,
* a bearer-only caller (no refresh cookie) revokes **all** families,
* an API-key caller → 403, unauthenticated → 401.
"""
from __future__ import annotations

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from auth_tenancy.rest import REFRESH_COOKIE_NAME
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

_SECRET = "test-secret-not-a-real-key"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
    AUTH_JWT_REFRESH_TTL_SECONDS=2592000,
    AUTH_COOKIE_SECURE=False,
    AUTH_LOGIN_INCLUDE_BODY_TOKEN=True,
)

_OLD = "Old-Passphrase-42"
_NEW = "New-Passphrase-77"

_URL = "/api/v1/auth/password/change/"


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="PW-T", slug="pw-t", is_active=True)


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    set_request_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name="PW-WS", preset={"name": "extended"}
        )
    finally:
        clear_request_tenant()


@pytest.fixture
def user(tenant: Tenant, workspace: Workspace) -> User:
    set_request_tenant(tenant.id)
    try:
        created = User.objects.create(
            username="pw-admin", email="pw-admin@t.test", tenant=tenant
        )
        created.set_password(_OLD)
        created.save(update_fields=["password"])
        UserRole.objects.create(
            tenant=tenant, user=created, workspace=workspace, role=ROLE_ADMIN
        )
        return created
    finally:
        clear_request_tenant()


def _login(client: APIClient) -> dict:
    response = client.post(
        "/api/v1/auth/login/",
        {"username": "pw-admin", "password": _OLD},
        format="json",
    )
    assert response.status_code == 200, response.content
    return response.json()


def _authed_client() -> APIClient:
    client = APIClient()
    _login(client)
    return client


def _change(client: APIClient, *, current: str = _OLD, new: str = _NEW):
    return client.post(
        _URL,
        {"current_password": current, "new_password": new},
        format="json",
    )


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_change_password_returns_204_and_rotates_the_credential(user):
    client = _authed_client()

    response = _change(client)
    assert response.status_code == 204, response.content

    fresh = APIClient()
    assert (
        fresh.post(
            "/api/v1/auth/login/",
            {"username": "pw-admin", "password": _NEW},
            format="json",
        ).status_code
        == 200
    )
    assert (
        APIClient()
        .post(
            "/api/v1/auth/login/",
            {"username": "pw-admin", "password": _OLD},
            format="json",
        )
        .status_code
        == 401
    )


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_wrong_current_password_is_a_400_and_does_not_leak(user):
    client = _authed_client()

    response = _change(client, current="not-the-password")
    assert response.status_code == 400
    body = response.json()["error"]
    assert body["code"] == "INVALID_CURRENT_PASSWORD"
    # Never echo the submitted or stored password.
    assert "not-the-password" not in response.content.decode()
    assert _OLD not in response.content.decode()


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_policy_violation_is_a_400_with_a_new_password_field_detail(user):
    client = _authed_client()

    response = _change(client, new="password123")
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "PASSWORD_POLICY_VIOLATION"
    field_errors = [d for d in error["details"] if d.get("field") == "new_password"]
    assert field_errors, error
    assert field_errors[0]["errors"], error


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_current_session_survives_while_other_session_is_revoked(user):
    current = _authed_client()
    other = _authed_client()

    response = _change(current)
    assert response.status_code == 204, response.content

    # The other session cannot extend itself any more.
    assert other.post("/api/v1/auth/refresh/", {}, format="json").status_code == 401
    # The session that changed the password still can.
    assert current.post("/api/v1/auth/refresh/", {}, format="json").status_code == 200


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_bearer_only_caller_revokes_every_session(user):
    cookie_client = _authed_client()
    access_token = _login(APIClient())["token"]

    bearer = APIClient()
    bearer.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    response = bearer.post(
        _URL,
        {"current_password": _OLD, "new_password": _NEW},
        format="json",
    )
    assert response.status_code == 204, response.content

    # No refresh cookie on the bearer call → no family is exempt, including the
    # cookie session's family.
    assert (
        cookie_client.post("/api/v1/auth/refresh/", {}, format="json").status_code
        == 401
    )
    # The refresh cookie is still present client-side; it is dead server-side.
    assert REFRESH_COOKIE_NAME in cookie_client.cookies


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_api_key_caller_is_refused_with_403(user):
    creator = _authed_client()
    created = creator.post(
        "/api/v1/api-keys/", {"name": "pw-change-key"}, format="json"
    )
    assert created.status_code == 201, created.content
    plaintext = created.json()["plaintext"]

    key_client = APIClient()
    key_client.credentials(HTTP_X_API_KEY=plaintext)
    response = key_client.post(
        _URL,
        {"current_password": _OLD, "new_password": _NEW},
        format="json",
    )
    assert response.status_code == 403
    assert (
        response.json()["error"]["code"]
        == "PASSWORD_CHANGE_REQUIRES_INTERACTIVE_SESSION"
    )


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_unauthenticated_caller_gets_401(user):
    response = APIClient().post(
        _URL,
        {"current_password": _OLD, "new_password": _NEW},
        format="json",
    )
    assert response.status_code == 401
