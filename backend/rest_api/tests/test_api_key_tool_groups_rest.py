# backend/rest_api/tests/test_api_key_tool_groups_rest.py
"""``scope`` / ``tool_groups`` on the API-key REST surface.

MCP-Modernisierung Phase D, Task 14. ``tool_groups`` is echoed back on create,
list and retrieve; it is catalogue curation only, so its validation is shape
only (a list of strings) — the HTTP layer does not check that a prefix exists,
because the catalogue grows with every tool group and a typo is a curation
mistake, not a security question.
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="AK-TG-T", slug="ak-tg-t", is_active=True)


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    set_request_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name="AK-TG-WS", preset={"name": "extended"}
        )
    finally:
        clear_request_tenant()


def _authed_admin(tenant: Tenant, workspace: Workspace) -> APIClient:
    """Create an admin user, log them in, return a Bearer-authenticated client."""
    set_request_tenant(tenant.id)
    try:
        user = User.objects.create(
            username="ak-tg-admin", email="ak-tg-admin@t.test", tenant=tenant
        )
        user.set_password("hunter2pass")
        user.save(update_fields=["password"])
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": "hunter2pass"},
        format="json",
    )
    assert login.status_code == 200, login.content
    token = login.json()["token"]
    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return authed


@pytest.mark.django_db
def test_create_defaults_to_write_scope_and_no_curation(tenant, workspace):
    client = _authed_admin(tenant, workspace)

    response = client.post("/api/v1/api-keys/", {"name": "default-key"}, format="json")

    assert response.status_code == 201, response.content
    assert response.json()["scope"] == "write"
    assert response.json()["tool_groups"] == []


@pytest.mark.django_db
def test_create_accepts_read_scope_and_tool_groups(tenant, workspace):
    client = _authed_admin(tenant, workspace)

    response = client.post(
        "/api/v1/api-keys/",
        {"name": "agent-key", "scope": "read", "tool_groups": ["requirement"]},
        format="json",
    )

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["scope"] == "read"
    assert body["tool_groups"] == ["requirement"]


@pytest.mark.django_db
def test_create_rejects_an_unknown_scope(tenant, workspace):
    client = _authed_admin(tenant, workspace)

    response = client.post(
        "/api/v1/api-keys/", {"name": "bad", "scope": "nonsense"}, format="json"
    )

    assert response.status_code == 400, response.content
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_create_rejects_non_list_tool_groups(tenant, workspace):
    client = _authed_admin(tenant, workspace)

    response = client.post(
        "/api/v1/api-keys/", {"name": "bad", "tool_groups": "requirement"}, format="json"
    )

    assert response.status_code == 400, response.content


@pytest.mark.django_db
def test_list_reports_scope_and_tool_groups(tenant, workspace):
    client = _authed_admin(tenant, workspace)
    created = client.post(
        "/api/v1/api-keys/",
        {"name": "listed", "scope": "read", "tool_groups": ["requirement"]},
        format="json",
    )
    assert created.status_code == 201, created.content

    response = client.get("/api/v1/api-keys/")

    assert response.status_code == 200, response.content
    payload = response.json()
    rows = payload["results"] if isinstance(payload, dict) else payload
    row = next(r for r in rows if r["name"] == "listed")
    assert row["scope"] == "read"
    assert row["tool_groups"] == ["requirement"]


@pytest.mark.django_db
def test_retrieve_reports_scope_and_tool_groups(tenant, workspace):
    client = _authed_admin(tenant, workspace)
    created = client.post(
        "/api/v1/api-keys/",
        {"name": "retrieved", "tool_groups": ["requirement", "icd"]},
        format="json",
    ).json()

    response = client.get(f"/api/v1/api-keys/{created['id']}/")

    assert response.status_code == 200, response.content
    assert response.json()["tool_groups"] == ["requirement", "icd"]
