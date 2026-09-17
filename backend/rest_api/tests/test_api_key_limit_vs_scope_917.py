"""#917 — the API-key scope gate must beat the API-key count limit.

QA finding on 1.8.0-beta.10: ``POST /api/v1/api-keys/`` with a read-scoped key
whose owner had reached the per-user cap answered ``400 "User already has the
maximum of N active API keys."`` instead of the 403 that names the real reason
(``"API key is read-only (scope='read'); operation 'write' requires
scope='write'."``). A client could not tell that its credential class may not
write at all.

Root cause: ``ApiKeyViewSet`` declares ``required_operation = Operation.READ``
(fix #716, so a Viewer can manage their own keys) and ``RbacPermission`` fed
exactly that declaration into the scope gate — a POST therefore looked like a
READ to the gate, which allowed it through to the view body and its limit
check.

Both halves are asserted here so the fix can regress neither into "the limit
was removed/weakened" nor into "the scope gate is bypassable again".

req_id : REQ-L2-RA-006, REQ-L3-AT001-003
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_EDITOR, UserRole
from auth_tenancy.services.authentication import AuthenticationService
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

_CREATE_URL = "/api/v1/api-keys/"


@pytest.fixture
def caller(db):
    """An Editor in an Extended workspace — holds both READ and WRITE."""
    tenant = Tenant.objects.create(
        name="T-917", slug=f"t-917-{uuid.uuid4().hex[:8]}", is_active=True
    )
    user = User.objects.create(
        username=f"u-917-{uuid.uuid4().hex[:8]}", email="u917@t.test", tenant=tenant
    )
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="WS-917", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_EDITOR
        )
    finally:
        clear_request_tenant()
    return tenant, user


def _client_with_key(tenant: Tenant, user: User, *, scope: str) -> APIClient:
    """Authenticate an APIClient with a freshly minted key of ``scope``."""
    result = AuthenticationService().create_api_key(
        user_id=user.id, tenant_id=tenant.id, name=f"917-{scope}", scope=scope
    )
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=result.plaintext)
    return client


@pytest.mark.django_db
def test_read_only_key_gets_403_not_400_when_cap_reached(caller, settings):
    """Cap reached + read-scoped key + POST -> 403 read-only, never the cap 400."""
    tenant, user = caller
    # cap = 1 and the read-scoped key below already fills it, so the limit
    # check would fire for any caller that gets past the scope gate.
    settings.MAX_ACTIVE_API_KEYS_PER_USER = 1
    client = _client_with_key(tenant, user, scope="read")

    resp = client.post(_CREATE_URL, {"name": "must-not-be-created"}, format="json")

    assert resp.status_code == 403, resp.content
    error = resp.json()["error"]
    assert "read-only" in error["message"]
    assert "write" in error["message"]
    # The wrong reason must not leak: that was the actual defect.
    assert "maximum" not in error["message"]


@pytest.mark.django_db
def test_authorized_write_key_still_hits_the_cap(caller, settings):
    """The cap is unchanged: a write-scoped key at the cap still gets its 400."""
    tenant, user = caller
    settings.MAX_ACTIVE_API_KEYS_PER_USER = 1
    client = _client_with_key(tenant, user, scope="write")

    resp = client.post(_CREATE_URL, {"name": "one-too-many"}, format="json")

    assert resp.status_code == 400, resp.content
    assert "maximum of 1 active API keys" in resp.json()["error"]["message"]


@pytest.mark.django_db
def test_authorized_write_key_below_cap_still_creates(caller, settings):
    """Control: the stricter scope gate did not over-reach on legitimate writes."""
    tenant, user = caller
    settings.MAX_ACTIVE_API_KEYS_PER_USER = 3
    client = _client_with_key(tenant, user, scope="write")

    resp = client.post(_CREATE_URL, {"name": "second-key"}, format="json")

    assert resp.status_code == 201, resp.content
    assert resp.json()["name"] == "second-key"
