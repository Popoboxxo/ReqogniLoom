"""
REST endpoint tests for ReqIF 1.2 import (REQ-147, COMP-AS-008b).

Tests POST /api/v1/workspaces/{id}/import/reqif/

Mirrors test_reqif_export.py's auth/JWT setup and test_csv_import.py's
file-upload patterns. Round-trips through the real GET .../export/reqif/
endpoint (REQ-146) to obtain a document, then POSTs it back via the import
endpoint under test.
"""
from __future__ import annotations

import io
import uuid

import pytest
from django.test import override_settings
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

_MALFORMED_REQIF = b"<not-a-valid-reqif><unclosed>"


@pytest.fixture
def reqif_import_admin_user(db):
    """Admin user with two workspaces; workspace_a gets one Need + one Requirement,
    workspace_b starts empty (used as the import target)."""
    tenant = Tenant.objects.create(
        name="Reqif-Import-Rest-T", slug="reqif-import-rest-t", is_active=True
    )
    user = User.objects.create(
        username="reqifimportadmin", email="reqifimportadmin@t.test", tenant=tenant
    )
    user.set_password("reqifpass123")
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace_a = Workspace.objects.create(
            tenant=tenant, name="Reqif-Import-WS-A", preset={"name": "standard"}
        )
        workspace_b = Workspace.objects.create(
            tenant=tenant, name="Reqif-Import-WS-B", preset={"name": "standard"}
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
            title="REST Import Need Alpha",
            description="Seeded via ORM for REST import round-trip test",
            category="functional",
            uid="NEED-IMP-001",
        )
        req_art = Artifact.objects.create(
            tenant=tenant, workspace=workspace_a, artifact_type="Requirement"
        )
        Requirement.objects.create(
            tenant=tenant,
            artifact=req_art,
            title="REST Import Req Alpha",
            description="Seeded via ORM for REST import round-trip test",
            category="functional",
            uid="REQ-IMP-001",
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


def _export_reqif(client: APIClient, workspace_id) -> bytes:
    resp = client.get(f"/api/v1/workspaces/{workspace_id}/export/reqif/")
    assert resp.status_code == 200
    return resp.content


# ---------------------------------------------------------------------------
# Success path — export from A, import into B
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_creates_entities_in_target_workspace(reqif_import_admin_user):
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    reqif_content = _export_reqif(client, workspace_a.id)

    reqif_file = io.BytesIO(reqif_content)
    reqif_file.name = "export.reqif"

    resp = client.post(
        f"/api/v1/workspaces/{workspace_b.id}/import/reqif/",
        {"file": reqif_file},
        format="multipart",
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["dry_run"] is False
    assert body["needs"]["created"] == 1
    assert body["requirements"]["created"] == 1
    assert body["needs"]["errors"] == []
    assert body["requirements"]["errors"] == []

    set_request_tenant(tenant.id)
    try:
        assert (
            StakeholderNeed.objects.filter(
                artifact__workspace=workspace_b, uid="NEED-IMP-001"
            ).count()
            == 1
        )
        assert (
            Requirement.objects.filter(
                artifact__workspace=workspace_b, uid="REQ-IMP-001"
            ).count()
            == 1
        )
    finally:
        clear_request_tenant()


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_reimport_same_document_is_idempotent(reqif_import_admin_user):
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    reqif_content = _export_reqif(client, workspace_a.id)

    for _ in range(2):
        reqif_file = io.BytesIO(reqif_content)
        reqif_file.name = "export.reqif"
        resp = client.post(
            f"/api/v1/workspaces/{workspace_b.id}/import/reqif/",
            {"file": reqif_file},
            format="multipart",
        )
        assert resp.status_code == 200

    body = resp.json()
    assert body["needs"]["created"] == 0
    assert body["needs"]["updated"] == 1
    assert body["requirements"]["created"] == 0
    assert body["requirements"]["updated"] == 1
    set_request_tenant(tenant.id)
    try:
        assert (
            StakeholderNeed.objects.filter(artifact__workspace=workspace_b).count()
            == 1
        )
        assert (
            Requirement.objects.filter(artifact__workspace=workspace_b).count() == 1
        )
    finally:
        clear_request_tenant()


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_dry_run_does_not_persist(reqif_import_admin_user):
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    reqif_content = _export_reqif(client, workspace_a.id)
    reqif_file = io.BytesIO(reqif_content)
    reqif_file.name = "export.reqif"

    resp = client.post(
        f"/api/v1/workspaces/{workspace_b.id}/import/reqif/?dry_run=true",
        {"file": reqif_file},
        format="multipart",
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["dry_run"] is True
    assert body["needs"]["created"] == 1
    assert body["requirements"]["created"] == 1

    set_request_tenant(tenant.id)
    try:
        assert (
            StakeholderNeed.objects.filter(artifact__workspace=workspace_b).count()
            == 0
        )
        assert (
            Requirement.objects.filter(artifact__workspace=workspace_b).count() == 0
        )
    finally:
        clear_request_tenant()


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_malformed_xml_returns_400(reqif_import_admin_user):
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    reqif_file = io.BytesIO(_MALFORMED_REQIF)
    reqif_file.name = "broken.reqif"

    resp = client.post(
        f"/api/v1/workspaces/{workspace_b.id}/import/reqif/",
        {"file": reqif_file},
        format="multipart",
    )

    assert resp.status_code == 400
    body = resp.json()
    assert "error" in body


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_without_file_returns_400(reqif_import_admin_user):
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    resp = client.post(
        f"/api/v1/workspaces/{workspace_b.id}/import/reqif/",
        {},
        format="multipart",
    )

    assert resp.status_code == 400
    body = resp.json()
    assert "error" in body


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_empty_file_returns_400(reqif_import_admin_user):
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    reqif_file = io.BytesIO(b"")
    reqif_file.name = "empty.reqif"

    resp = client.post(
        f"/api/v1/workspaces/{workspace_b.id}/import/reqif/",
        {"file": reqif_file},
        format="multipart",
    )

    assert resp.status_code == 400


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_unknown_workspace_returns_404(reqif_import_admin_user):
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    reqif_content = _export_reqif(client, workspace_a.id)
    reqif_file = io.BytesIO(reqif_content)
    reqif_file.name = "export.reqif"

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/import/reqif/",
        {"file": reqif_file},
        format="multipart",
    )

    assert resp.status_code == 404


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_requires_auth(reqif_import_admin_user):
    """Unauthenticated request is rejected (401 or 403, matches test_reqif_export.py)."""
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()

    reqif_file = io.BytesIO(_MALFORMED_REQIF)
    reqif_file.name = "broken.reqif"

    resp = client.post(
        f"/api/v1/workspaces/{workspace_b.id}/import/reqif/",
        {"file": reqif_file},
        format="multipart",
    )

    assert resp.status_code in (401, 403)
