"""
REST endpoint tests for PDF report generation (REQ-L2-AS-016).

Tests GET /api/v1/workspaces/{id}/reports/pdf/?layout=...
"""
from __future__ import annotations

import uuid

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    Artifact,
    Requirement,
    Tenant,
    User,
    Workspace,
)

_SECRET = "test-secret-not-a-real-key"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


@pytest.fixture
def pdf_admin_user(db):
    """Admin user with a workspace containing requirements."""
    tenant = Tenant.objects.create(
        name="PDF-Test-T", slug="pdf-test-t", is_active=True
    )
    user = User.objects.create(
        username="pdfadmin", email="pdfadmin@t.test", tenant=tenant
    )
    user.set_password("pdfpass123")
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="PDF-WS", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
        # Create a requirement in the workspace
        artifact = Artifact.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type="requirement",
        )
        Requirement.objects.create(
            tenant=tenant,
            artifact=artifact,
            title="PDF-Test-Requirement",
            category="functional",
        )
    finally:
        clear_request_tenant()

    return user, tenant, workspace


def _login(client: APIClient, username: str, password: str) -> str:
    """Login and return the bearer token."""
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": username, "password": password},
        format="json",
    )
    assert resp.status_code == 200
    return resp.json()["token"]


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_pdf_report_endpoint_returns_pdf(pdf_admin_user):
    """GET /api/v1/workspaces/{id}/reports/pdf/ returns a PDF download."""
    user, tenant, workspace = pdf_admin_user
    client = APIClient()
    token = _login(client, "pdfadmin", "pdfpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    resp = client.get(
        f"/api/v1/workspaces/{workspace.id}/reports/pdf/",
        {"layout": "requirement_document"},
    )

    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/pdf"
    assert "attachment" in resp.get("Content-Disposition", "")
    # PDF magic bytes
    assert resp.content[:5] == b"%PDF-"
    assert len(resp.content) > 1024


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_pdf_report_endpoint_traceability_matrix(pdf_admin_user):
    """GET with layout=traceability_matrix also returns a valid PDF."""
    user, tenant, workspace = pdf_admin_user
    client = APIClient()
    token = _login(client, "pdfadmin", "pdfpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    resp = client.get(
        f"/api/v1/workspaces/{workspace.id}/reports/pdf/",
        {"layout": "traceability_matrix"},
    )

    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/pdf"
    assert resp.content[:5] == b"%PDF-"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_pdf_report_endpoint_invalid_layout(pdf_admin_user):
    """Invalid layout returns 400."""
    user, tenant, workspace = pdf_admin_user
    client = APIClient()
    token = _login(client, "pdfadmin", "pdfpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    resp = client.get(
        f"/api/v1/workspaces/{workspace.id}/reports/pdf/",
        {"layout": "invalid_layout"},
    )

    assert resp.status_code == 400


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_pdf_report_endpoint_unauthenticated():
    """Unauthenticated request returns 401 or 403."""
    client = APIClient()
    fake_ws_id = uuid.uuid4()
    resp = client.get(f"/api/v1/workspaces/{fake_ws_id}/reports/pdf/")
    # DRF returns 403 when no credentials are provided at all
    assert resp.status_code in (401, 403)
