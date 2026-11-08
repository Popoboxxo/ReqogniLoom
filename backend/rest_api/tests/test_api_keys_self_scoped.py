# backend/rest_api/tests/test_api_keys_self_scoped.py
"""Regression guard for issue #1731: ``/api/v1/api-keys/`` is self-scoped.

The issue suspected a Viewer could read the workspace's "credential landscape".
Verified false: the service filters ``ApiKey.unscoped.filter(user_id=...)``
(``auth_tenancy/services/authentication.py``), so the route only ever returns
the caller's own keys — the deliberate self-service rule from #716.

This module turns that reasoning into a machine-checked contract:

* user A sees only their own keys, user B sees zero of A's,
* a Viewer may list their own keys (200) — the RBAC exemption is intentional,
* a foreign ``pk`` answers 404 (not 403: it must not confirm existence),
* keys never cross a tenant boundary.

No behaviour is changed by the fix; this is the regression net the issue asked
for.
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_VIEWER, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

_URL = "/api/v1/api-keys/"


def _make_member(tenant: Tenant, *, name: str, role: str = ROLE_VIEWER) -> User:
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=f"WS-{name}", preset={"name": "extended"}
        )
        user = User.objects.create(
            username=name, email=f"{name}@t.test", tenant=tenant
        )
        user.set_password("hunter2pass")
        user.save(update_fields=["password"])
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=role
        )
        return user
    finally:
        clear_request_tenant()


def _client_for(user: User) -> APIClient:
    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": "hunter2pass"},
        format="json",
    )
    assert login.status_code == 200, login.content
    return client


def _create_key(client: APIClient, name: str) -> dict:
    # `scope="read"` on purpose: all actors here are Viewers, and #1608 bounds
    # the key's capability tier by the creator's own rights — a write-capable
    # key from a Viewer is refused before this test's concern (isolation) is
    # even reached.
    response = client.post(_URL, {"name": name, "scope": "read"}, format="json")
    assert response.status_code == 201, response.content
    return response.json()


@pytest.fixture
def tenant_a(db) -> Tenant:
    return Tenant.objects.create(name="AK-A", slug="ak-self-a", is_active=True)


@pytest.fixture
def tenant_b(db) -> Tenant:
    return Tenant.objects.create(name="AK-B", slug="ak-self-b", is_active=True)


@pytest.mark.django_db
def test_a_user_never_sees_another_users_keys(tenant_a):
    alice = _make_member(tenant_a, name="ak-alice")
    bob = _make_member(tenant_a, name="ak-bob")

    created = _create_key(_client_for(alice), "alice-only")
    alice_list = _client_for(alice).get(_URL)
    bob_list = _client_for(bob).get(_URL)

    assert alice_list.status_code == 200
    assert [k["id"] for k in alice_list.json()["results"]] == [created["id"]]
    assert bob_list.status_code == 200
    assert bob_list.json()["results"] == []
    assert bob_list.json()["count"] == 0


@pytest.mark.django_db
def test_a_viewer_may_read_only_their_own_keys(tenant_a):
    """The RBAC exemption from #716 is intentional and stays as-is."""
    alice = _make_member(tenant_a, name="ak-viewer-alice", role=ROLE_VIEWER)
    _create_key(_client_for(alice), "viewer-key")

    response = _client_for(alice).get(_URL)

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["results"][0]["name"] == "viewer-key"


@pytest.mark.django_db
def test_foreign_key_id_answers_404_not_403(tenant_a):
    alice = _make_member(tenant_a, name="ak-owner")
    bob = _make_member(tenant_a, name="ak-intruder")

    created = _create_key(_client_for(alice), "private-key")

    response = _client_for(bob).get(f"{_URL}{created['id']}/")

    # 404, not 403: a foreign id must not confirm that the key exists.
    assert response.status_code == 404


@pytest.mark.django_db
def test_keys_do_not_cross_the_tenant_boundary(tenant_a, tenant_b):
    alice_a = _make_member(tenant_a, name="ak-tenant-a")
    bob_b = _make_member(tenant_b, name="ak-tenant-b")

    created = _create_key(_client_for(alice_a), "tenant-a-key")

    listing = _client_for(bob_b).get(_URL)
    detail = _client_for(bob_b).get(f"{_URL}{created['id']}/")

    assert listing.status_code == 200
    assert listing.json()["results"] == []
    assert detail.status_code == 404
