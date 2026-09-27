"""GitHub #1076 — an invalid ``X-API-Key`` must be *legible*, not just rejected.

Observed before the fix (a valid ``Authorization: Bearer`` token on every
request, ``GET /api/v1/workspaces/``)::

    X-API-Key: rf_kom…sch  -> 401 {"error": {"code": "invalid_api_key", …}}
    X-API-Key: <valid>     -> 200
    X-API-Key: (empty)     -> 200
    (no Bearer at all)    -> 401

The status codes were never the complaint. A 401 whose message reads "The
provided API key is invalid." is indistinguishable from a session timeout, and
a reverse proxy that injects a stale key for one upstream service silently kills
every session behind it.

The decision taken (documented on
:class:`auth_tenancy.rest.AuthTenancyAuthentication`) is **fail-closed** — the
invalid key is still *not* ignored — plus the missing half: the 401 now says
which header caused the rejection and that the ``Bearer`` credential was never
evaluated. These tests pin all four legs of that contract, plus the boundaries
that keep it honest:

* the machine-readable ``code`` and the HTTP status are unchanged;
* an empty header is still "not present" (200 with the Bearer token);
* the ``Authorization: Bearer reqlo_…`` transport keeps the generic text,
  because "remove the X-API-Key header" would be wrong advice for it;
* the message leaks nothing about whether the key exists.
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, ApiKey, UserRole
from auth_tenancy.services.authentication import (
    generate_api_key_plaintext,
    hash_api_key,
)
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

pytestmark = pytest.mark.django_db

_LIST_URL = "/api/v1/workspaces/"

#: An unknown key value. Only the ``reqlo_`` prefix is transport-significant
#: (see ``AuthTenancyAuthentication._extract_and_validate``), so this shape is
#: deliberately *not* one — the issue report used an ``rf_``-prefixed value and
#: the header is read verbatim either way.
_UNKNOWN_KEY = "rf_komegadschluessel1234567890abcdef"


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="K1076-T", slug="k1076-t", is_active=True)


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    set_request_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant=tenant, name="K1076-WS", preset={"name": "standard"})
    finally:
        clear_request_tenant()


@pytest.fixture
def bearer_client(tenant: Tenant, workspace: Workspace) -> tuple[APIClient, User]:
    """A client holding a genuinely valid Bearer token for a real user."""
    set_request_tenant(tenant.id)
    try:
        user = User.objects.create(
            username="k1076-admin", email="k1076-admin@t.test", tenant=tenant
        )
        user.set_password("hunter2pass")
        user.save(update_fields=["password"])
        UserRole.objects.create(tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN)
    finally:
        clear_request_tenant()

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": "k1076-admin", "password": "hunter2pass"},
        format="json",
    )
    assert login.status_code == 200, login.content

    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return authed, user


def _issue_key(user: User, tenant: Tenant) -> str:
    plaintext = generate_api_key_plaintext()
    ApiKey.unscoped.create(tenant=tenant, user=user, name="k1076", key_hash=hash_api_key(plaintext))
    return plaintext


# ---------------------------------------------------------------------------
# 1. The invalid key + valid Bearer case — the one the issue is about
# ---------------------------------------------------------------------------


def test_invalid_key_with_valid_bearer_is_401_with_an_legible_message(
    bearer_client, tenant, workspace
):
    authed, _user = bearer_client

    response = authed.get(_LIST_URL, HTTP_X_API_KEY=_UNKNOWN_KEY)

    assert response.status_code == 401, response.content
    error = response.json()["error"]
    # The code and the status are the stable contract — unchanged by #1076.
    assert error["code"] == "invalid_api_key"
    message = error["message"]
    # The rejection is attributed to the header, not left open to interpretation.
    assert "X-API-Key" in message
    assert "not valid" in message
    # And the operator is told the escape hatch.
    assert "Authorization: Bearer" in message
    assert "was NOT evaluated" in message
    assert "remove the X-API-Key header" in message
    # No oracle: nothing about existence, ownership or expiry leaks.
    assert "unknown" not in message.lower()
    assert "not found" not in message.lower()
    assert "revoked" not in message.lower()
    assert "expired" not in message.lower()


def test_the_legible_message_is_localised(bearer_client):
    authed, _user = bearer_client

    response = authed.get(
        _LIST_URL, HTTP_X_API_KEY=_UNKNOWN_KEY, HTTP_ACCEPT_LANGUAGE="de-DE,de;q=0.9"
    )

    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == "invalid_api_key"
    assert "X-API-Key" in error["message"]
    assert "Bearer" in error["message"]
    assert "entfernen Sie den X-API-Key-Header" in error["message"]


# ---------------------------------------------------------------------------
# 2. The other two legs — the behaviour must not drift
# ---------------------------------------------------------------------------


def test_valid_key_with_valid_bearer_is_200(bearer_client, tenant):
    authed, user = bearer_client

    response = authed.get(_LIST_URL, HTTP_X_API_KEY=_issue_key(user, tenant))

    assert response.status_code == 200, response.content


def test_empty_key_with_valid_bearer_is_200(bearer_client):
    """An empty header is "not present", so the Bearer token is used."""
    authed, _user = bearer_client

    response = authed.get(_LIST_URL, HTTP_X_API_KEY="")

    assert response.status_code == 200, response.content


def test_unknown_key_without_bearer_names_the_header_and_says_unauthenticated():
    """No ``Authorization`` header, so the remediation must differ.

    "Remove the X-API-Key header to authenticate with the Bearer token" would
    be actively wrong here: this request has no Bearer token, so removing the
    only credential would leave it anonymous. The message therefore names the
    header as the cause and states the request is unauthenticated.
    """
    response = APIClient().get(_LIST_URL, HTTP_X_API_KEY=_UNKNOWN_KEY)

    assert response.status_code == 401, response.content
    error = response.json()["error"]
    assert error["code"] == "invalid_api_key"
    message = error["message"]
    assert "X-API-Key" in message
    assert "No other credential was presented" in message
    assert "unauthenticated" in message
    # The Bearer-fallback advice must NOT be offered when there is no Bearer.
    assert "remove the X-API-Key header to authenticate" not in message


# ---------------------------------------------------------------------------
# 3. The boundaries that keep the message honest
# ---------------------------------------------------------------------------


def test_bearer_carried_reqlo_key_keeps_the_generic_message():
    """``Authorization: Bearer reqlo_…`` is a different transport.

    "Remove the X-API-Key header" would be actively wrong advice for a request
    that has no such header, so this path must keep the catalogue text even
    though the rejection has the identical code and status.
    """
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer reqlo_{_UNKNOWN_KEY}")

    response = client.get(_LIST_URL)

    assert response.status_code == 401, response.content
    error = response.json()["error"]
    assert error["code"] == "invalid_api_key"
    assert error["message"] == "The provided API key is invalid."


def test_revoked_key_keeps_its_own_self_describing_code(bearer_client, tenant):
    """``api_key_revoked`` already names its cause and its fix.

    Deliberately out of scope for #1076: the operator's action ("rotate the
    key") is already unambiguous, and a more specific message would start
    revealing key state.
    """
    authed, user = bearer_client
    plaintext = _issue_key(user, tenant)
    set_request_tenant(tenant.id)
    try:
        ApiKey.unscoped.filter(key_hash=hash_api_key(plaintext)).update(
            revoked_at="2026-01-01T00:00:00Z"
        )
    finally:
        clear_request_tenant()

    response = authed.get(_LIST_URL, HTTP_X_API_KEY=plaintext)

    assert response.status_code == 401, response.content
    error = response.json()["error"]
    assert error["code"] == "api_key_revoked"
    assert error["message"] == "The provided API key has been revoked."


def test_message_override_does_not_change_code_or_status():
    """Unit-level guard on the plumbing itself.

    The override is a *message* concern only. If it ever started moving the
    status or the code, every client branch on ``invalid_api_key`` would break
    silently.
    """
    from auth_tenancy.errors import AuthenticationFailed, error_response_tuple

    error = AuthenticationFailed("invalid_api_key", message="custom text")

    body, status_code = error_response_tuple(error)

    assert status_code == 401
    assert body["error"]["code"] == "invalid_api_key"
    assert body["error"]["message"] == "custom text"
    # details[0] is unchanged: the override must not drop the doc_url contract.
    assert body["error"]["details"][0]["doc_url"].endswith("/invalid_api_key")
