"""
REST endpoint tests for ReqIF 1.2 export (REQ-146, COMP-AS-008).

Tests GET /api/v1/workspaces/{id}/export/reqif/
"""
from __future__ import annotations

import pytest
from django.test import override_settings
from reqif.parser import ReqIFParser
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, StakeholderNeed, Tenant, User, Workspace

_SECRET = "test-secret-not-a-real-key"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


@pytest.fixture
def reqif_admin_user(db):
    """Admin user with two workspaces; workspace_a gets one Need + one Requirement."""
    tenant = Tenant.objects.create(
        name="Reqif-Rest-T", slug="reqif-rest-t", is_active=True
    )
    user = User.objects.create(
        username="reqifadmin", email="reqifadmin@t.test", tenant=tenant
    )
    user.set_password("reqifpass123")
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace_a = Workspace.objects.create(
            tenant=tenant, name="Reqif-WS-A", preset={"name": "standard"}
        )
        workspace_b = Workspace.objects.create(
            tenant=tenant, name="Reqif-WS-B", preset={"name": "standard"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace_a, role=ROLE_ADMIN
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace_b, role=ROLE_ADMIN
        )

        need_art = Artifact.objects.create(
            tenant=tenant, workspace=workspace_a, artifact_type="StakeholderNeed"
        )
        StakeholderNeed.objects.create(
            tenant=tenant,
            artifact=need_art,
            title="REST Need Alpha",
            description="Seeded via ORM for REST export test",
            category="functional",
            status="draft",
            uid="NEED-REST-001",
        )
        req_art = Artifact.objects.create(
            tenant=tenant, workspace=workspace_a, artifact_type="Requirement"
        )
        Requirement.objects.create(
            tenant=tenant,
            artifact=req_art,
            title="REST Req Alpha",
            description="Seeded via ORM for REST export test",
            category="functional",
            status="draft",
            uid="REQ-REST-001",
        )
    finally:
        clear_request_tenant()

    return user, tenant, workspace_a, workspace_b


def _login(client: APIClient, username: str, password: str) -> str:
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": username, "password": password},
        format="json",
    )
    assert resp.status_code == 200
    return resp.json()["token"]


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_export_returns_valid_document(reqif_admin_user):
    user, tenant, workspace_a, workspace_b = reqif_admin_user
    client = APIClient()
    token = _login(client, "reqifadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    resp = client.get(f"/api/v1/workspaces/{workspace_a.id}/export/reqif/")

    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/xml"
    assert "attachment" in resp["Content-Disposition"]
    assert ".reqif" in resp["Content-Disposition"]

    bundle = ReqIFParser.parse_from_string(resp.content.decode("utf-8"))
    content = bundle.core_content.req_if_content
    assert len(content.spec_objects) == 2
    titles = {
        so.attribute_map["ATTR-TITLE"].value for so in content.spec_objects
    }
    assert titles == {"REST Need Alpha", "REST Req Alpha"}


# ---------------------------------------------------------------------------
# Workspace scoping
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_export_filters_by_workspace(reqif_admin_user):
    """Export of an empty sibling workspace must not leak workspace_a's data."""
    user, tenant, workspace_a, workspace_b = reqif_admin_user
    client = APIClient()
    token = _login(client, "reqifadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    resp = client.get(f"/api/v1/workspaces/{workspace_b.id}/export/reqif/")

    assert resp.status_code == 200
    bundle = ReqIFParser.parse_from_string(resp.content.decode("utf-8"))
    content = bundle.core_content.req_if_content
    assert content.spec_objects == []


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_export_unknown_workspace_returns_404(reqif_admin_user):
    import uuid

    user, tenant, workspace_a, workspace_b = reqif_admin_user
    client = APIClient()
    token = _login(client, "reqifadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    resp = client.get(f"/api/v1/workspaces/{uuid.uuid4()}/export/reqif/")

    assert resp.status_code == 404


@pytest.mark.django_db
def test_reqif_export_requires_auth(reqif_admin_user):
    """Unauthenticated request is rejected (DRF returns 403 when no credentials
    are provided at all; see test_pdf_report_endpoint.py for the same pattern)."""
    user, tenant, workspace_a, workspace_b = reqif_admin_user
    client = APIClient()

    resp = client.get(f"/api/v1/workspaces/{workspace_a.id}/export/reqif/")

    assert resp.status_code in (401, 403)
