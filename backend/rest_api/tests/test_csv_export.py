"""
REST endpoint tests for CSV export (REQ-L3-EXP-002, C7 frontend-feedback Cluster C).

Tests GET /api/v1/workspaces/{id}/export/csv/
"""
from __future__ import annotations

import io

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

_VALID_CSV = b"title,description,category,status\nReq Alpha,First requirement,functional,draft\n"


@pytest.fixture
def export_admin_user(db):
    """Admin user with two workspaces for CSV export tests."""
    tenant = Tenant.objects.create(
        name="Export-Test-T", slug="export-test-t", is_active=True
    )
    user = User.objects.create(
        username="exportadmin", email="exportadmin@t.test", tenant=tenant
    )
    user.set_password("exportpass123")
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace_a = Workspace.objects.create(
            tenant=tenant, name="Export-WS-A", preset={"name": "standard"}
        )
        workspace_b = Workspace.objects.create(
            tenant=tenant, name="Export-WS-B", preset={"name": "standard"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace_a, role=ROLE_ADMIN
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace_b, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()

    return user, tenant, workspace_a, workspace_b


def _login(client: APIClient, username: str, password: str) -> str:
    """Login and return the bearer token."""
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": username, "password": password},
        format="json",
    )
    assert resp.status_code == 200
    return resp.json()["token"]


def _import_requirement(client: APIClient, workspace_id) -> None:
    """Seed one Requirement into a workspace via the (already tested) CSV import endpoint."""
    csv_file = io.BytesIO(_VALID_CSV)
    csv_file.name = "seed.csv"
    resp = client.post(
        f"/api/v1/workspaces/{workspace_id}/import/csv/",
        {"file": csv_file, "entity_type": "Requirement"},
        format="multipart",
    )
    assert resp.status_code == 201, resp.content


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_requirements_export_returns_csv(export_admin_user):
    """GET export/csv?entity_type=Requirement returns a CSV file with the seeded row."""
    user, tenant, workspace_a, workspace_b = export_admin_user
    client = APIClient()
    token = _login(client, "exportadmin", "exportpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    _import_requirement(client, workspace_a.id)

    resp = client.get(
        f"/api/v1/workspaces/{workspace_a.id}/export/csv/",
        {"entity_type": "Requirement"},
    )

    assert resp.status_code == 200
    assert resp["Content-Type"] == "text/csv"
    assert "attachment" in resp["Content-Disposition"]
    content = resp.content.decode("utf-8")
    assert "Req Alpha" in content
    assert "terminology_profile" in content


# ---------------------------------------------------------------------------
# Workspace scoping
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_requirements_export_filters_by_workspace(export_admin_user):
    """Export only returns rows belonging to the requested workspace."""
    user, tenant, workspace_a, workspace_b = export_admin_user
    client = APIClient()
    token = _login(client, "exportadmin", "exportpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    # Seed a requirement only into workspace_a.
    _import_requirement(client, workspace_a.id)

    # Exporting workspace_b must not contain workspace_a's data.
    resp = client.get(
        f"/api/v1/workspaces/{workspace_b.id}/export/csv/",
        {"entity_type": "Requirement"},
    )

    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    assert "Req Alpha" not in content


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_export_missing_entity_type_returns_400(export_admin_user):
    """GET export/csv without entity_type returns 400."""
    user, tenant, workspace_a, workspace_b = export_admin_user
    client = APIClient()
    token = _login(client, "exportadmin", "exportpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    resp = client.get(f"/api/v1/workspaces/{workspace_a.id}/export/csv/")

    assert resp.status_code == 400
    body = resp.json()
    assert "error" in body


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_export_invalid_entity_type_returns_400(export_admin_user):
    """GET export/csv with an unsupported entity_type returns 400."""
    user, tenant, workspace_a, workspace_b = export_admin_user
    client = APIClient()
    token = _login(client, "exportadmin", "exportpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    resp = client.get(
        f"/api/v1/workspaces/{workspace_a.id}/export/csv/",
        {"entity_type": "NotAType"},
    )

    assert resp.status_code == 400
    body = resp.json()
    assert "Unsupported entity_type" in body["error"]["message"]


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_stakeholder_need_export_returns_csv(export_admin_user):
    """GET export/csv?entity_type=StakeholderNeed returns 200 with an empty CSV (no needs seeded)."""
    user, tenant, workspace_a, workspace_b = export_admin_user
    client = APIClient()
    token = _login(client, "exportadmin", "exportpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    resp = client.get(
        f"/api/v1/workspaces/{workspace_a.id}/export/csv/",
        {"entity_type": "StakeholderNeed"},
    )

    assert resp.status_code == 200
    assert resp["Content-Type"] == "text/csv"
