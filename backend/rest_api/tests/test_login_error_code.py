"""Issue #271: login credential rejection must not reuse ``invalid_token``.

``invalid_token`` means "the JWT you presented could not be parsed / has
expired". Reusing it for "your username or password is wrong" left anyone
debugging a failing API call unable to tell an expired access token from a
login problem.

The split introduces ``invalid_credentials`` for the login-endpoint family
while keeping ``invalid_token`` reserved for JWT parse/expiry failures.

The anti-enumeration property is unchanged and re-asserted here: unknown user,
wrong password and inactive user must all produce a *byte-identical* response,
so an attacker cannot use the login endpoint to discover which usernames exist.

Shape note (systemaudit 2026-08-27, P1 item 13): the auth error body is now the
project-wide envelope ``{"error": {"code", "message", "details"}}``, so the code
is read from ``response.data["error"]["code"]`` rather than ``["error"]``. The
codes themselves are unchanged — this file is about *which* code is returned.
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from persistence.models import Tenant, User

pytestmark = pytest.mark.django_db

LOGIN_URL = "/api/v1/auth/login/"


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="LoginErrTenant")


def _user(tenant, username: str, password: str, *, is_active: bool = True) -> User:
    user = User.objects.create(
        username=username,
        email=f"{username}@example.test",
        tenant=tenant,
        is_active=is_active,
    )
    user.set_password(password)
    user.save(update_fields=["password"])
    return user


def _login(username, password):
    return APIClient().post(
        LOGIN_URL, {"username": username, "password": password}, format="json"
    )


# ---------------------------------------------------------------------------
# The new code
# ---------------------------------------------------------------------------


def test_wrong_password_returns_invalid_credentials(tenant):
    _user(tenant, "alice", "correct-horse")

    response = _login("alice", "wrong-password")

    assert response.status_code == 401
    assert response.data["error"]["code"] == "invalid_credentials"


def test_unknown_user_returns_invalid_credentials(tenant):
    response = _login("nobody-at-all", "whatever")

    assert response.status_code == 401
    assert response.data["error"]["code"] == "invalid_credentials"


def test_inactive_user_returns_invalid_credentials(tenant):
    _user(tenant, "ghost", "correct-horse", is_active=False)

    response = _login("ghost", "correct-horse")

    assert response.status_code == 401
    assert response.data["error"]["code"] == "invalid_credentials"


def test_missing_credentials_returns_invalid_credentials(tenant):
    response = APIClient().post(LOGIN_URL, {}, format="json")

    assert response.status_code == 401
    assert response.data["error"]["code"] == "invalid_credentials"


def test_login_never_reports_invalid_token(tenant):
    """``invalid_token`` must no longer appear on the login endpoint at all."""
    _user(tenant, "alice2", "correct-horse")

    for username, password in [
        ("alice2", "wrong"),
        ("does-not-exist", "wrong"),
        ("", ""),
    ]:
        response = _login(username, password)
        assert response.data["error"]["code"] != "invalid_token"


# ---------------------------------------------------------------------------
# Anti-enumeration: the whole point of sharing ONE code across the family
# ---------------------------------------------------------------------------


def test_unknown_user_and_wrong_password_are_byte_identical(tenant):
    """The deliberate anti-enumeration property (password_authentication.py).

    An attacker probing usernames must not be able to tell "no such user" from
    "user exists, wrong password" — not via the code, the message, the status,
    or any other byte of the response body.
    """
    _user(tenant, "realuser", "correct-horse")

    wrong_password = _login("realuser", "definitely-wrong")
    unknown_user = _login("definitely-no-such-user", "definitely-wrong")

    assert wrong_password.status_code == unknown_user.status_code == 401
    wrong_password.render()
    unknown_user.render()
    assert wrong_password.content == unknown_user.content


def test_inactive_user_is_indistinguishable_from_the_others(tenant):
    _user(tenant, "realuser2", "correct-horse")
    _user(tenant, "inactive2", "correct-horse", is_active=False)

    wrong_password = _login("realuser2", "definitely-wrong")
    inactive = _login("inactive2", "correct-horse")

    assert wrong_password.status_code == inactive.status_code == 401
    wrong_password.render()
    inactive.render()
    assert wrong_password.content == inactive.content


# ---------------------------------------------------------------------------
# invalid_token stays reserved for real JWT failures
# ---------------------------------------------------------------------------


def test_malformed_bearer_token_on_protected_endpoint_still_says_invalid_token():
    """The other half of the split: JWT parse failures keep ``invalid_token``."""
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer this.is.not.a.jwt")

    response = client.get("/api/v1/workspaces/")

    assert response.status_code == 401
    assert response.data["error"]["code"] == "invalid_token"


def test_the_two_failure_classes_are_now_distinguishable(tenant):
    """The actual bug in #271: one code could not tell the two apart."""
    _user(tenant, "alice3", "correct-horse")

    login_failure = _login("alice3", "wrong")

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer this.is.not.a.jwt")
    token_failure = client.get("/api/v1/workspaces/")

    assert login_failure.data["error"]["code"] != token_failure.data["error"]["code"]
