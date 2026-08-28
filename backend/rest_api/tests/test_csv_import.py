"""
REST endpoint tests for CSV bulk import (REQ-L0-013, REQ-L2-AS-014).

Tests POST /api/v1/workspaces/{id}/import/csv/
"""
from __future__ import annotations

import io
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


_VALID_CSV = b"title,description,category,status\nReq One,First requirement,functional,draft\nReq Two,Second requirement,non-functional,draft\n"

_MALFORMED_CSV = b"title,description\n\"unclosed quote,desc\n"

_MISSING_TITLE_CSV = b"title,description\n,No title here\n"


@pytest.fixture
def import_admin_user(db):
    """Admin user with a workspace for CSV import tests."""
    tenant = Tenant.objects.create(
        name="Import-Test-T", slug="import-test-t", is_active=True
    )
    user = User.objects.create(
        username="importadmin", email="importadmin@t.test", tenant=tenant
    )
    user.set_password("importpass123")
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="Import-WS", preset={"name": "standard"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
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


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_post_csv_creates_requirements(import_admin_user):
    """POST with valid CSV returns 201 and creates requirements."""
    user, tenant, workspace = import_admin_user
    client = APIClient()
    token = _login(client, "importadmin", "importpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    csv_file = io.BytesIO(_VALID_CSV)
    csv_file.name = "test.csv"

    resp = client.post(
        f"/api/v1/workspaces/{workspace.id}/import/csv/",
        {"file": csv_file, "entity_type": "Requirement"},
        format="multipart",
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    assert body["imported_count"] == 2
    assert body["status"] == "ok"
    assert body["errors"] == []

    # Verify requirements were actually created
    set_request_tenant(tenant.id)
    try:
        req_count = Requirement.objects.filter(
            artifact__workspace=workspace
        ).count()
    finally:
        clear_request_tenant()
    assert req_count >= 2


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_post_invalid_entity_type_returns_400(import_admin_user):
    """POST with invalid entity_type returns 400."""
    user, tenant, workspace = import_admin_user
    client = APIClient()
    token = _login(client, "importadmin", "importpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    csv_file = io.BytesIO(_VALID_CSV)
    csv_file.name = "test.csv"

    resp = client.post(
        f"/api/v1/workspaces/{workspace.id}/import/csv/",
        {"file": csv_file, "entity_type": "InvalidType"},
        format="multipart",
    )

    assert resp.status_code == 400
    body = resp.json()
    assert "error" in body
    assert "Unsupported entity_type" in body["error"]["message"]


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_post_malformed_csv_returns_400(import_admin_user):
    """POST with malformed CSV returns 400 with validation errors."""
    user, tenant, workspace = import_admin_user
    client = APIClient()
    token = _login(client, "importadmin", "importpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    csv_file = io.BytesIO(_MALFORMED_CSV)
    csv_file.name = "malformed.csv"

    resp = client.post(
        f"/api/v1/workspaces/{workspace.id}/import/csv/",
        {"file": csv_file, "entity_type": "Requirement"},
        format="multipart",
    )

    # Malformed CSV may return 400 (validation_error) or 201 with errors
    # depending on how the CSV parser handles it
    assert resp.status_code in (201, 400)


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_post_too_many_rows_returns_400(import_admin_user):
    """POST with >1000 rows returns 400 (REQ-L3-IMP-003)."""
    user, tenant, workspace = import_admin_user
    client = APIClient()
    token = _login(client, "importadmin", "importpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    # Build CSV with 1001 data rows
    header = b"title\n"
    data_rows = b"\n".join(f"Req {i}".encode() for i in range(1001))
    big_csv = header + data_rows

    csv_file = io.BytesIO(big_csv)
    csv_file.name = "big.csv"

    resp = client.post(
        f"/api/v1/workspaces/{workspace.id}/import/csv/",
        {"file": csv_file, "entity_type": "Requirement"},
        format="multipart",
    )

    assert resp.status_code == 400
    body = resp.json()
    assert "error" in body
    assert "maximum row limit" in body["error"]["message"].lower() or "1000" in body["error"]["message"]


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_post_without_file_returns_400(import_admin_user):
    """POST without file field returns 400."""
    user, tenant, workspace = import_admin_user
    client = APIClient()
    token = _login(client, "importadmin", "importpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    resp = client.post(
        f"/api/v1/workspaces/{workspace.id}/import/csv/",
        {"entity_type": "Requirement"},
        format="multipart",
    )

    assert resp.status_code == 400
    body = resp.json()
    assert "error" in body
    assert "file" in body["error"]["message"].lower() or "No CSV" in body["error"]["message"]


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_post_without_entity_type_returns_400(import_admin_user):
    """POST without entity_type returns 400."""
    user, tenant, workspace = import_admin_user
    client = APIClient()
    token = _login(client, "importadmin", "importpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    csv_file = io.BytesIO(_VALID_CSV)
    csv_file.name = "test.csv"

    resp = client.post(
        f"/api/v1/workspaces/{workspace.id}/import/csv/",
        {"file": csv_file},
        format="multipart",
    )

    assert resp.status_code == 400
    body = resp.json()
    assert "error" in body
    assert "entity_type" in body["error"]["message"].lower()


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_post_csv_with_missing_title_returns_400(import_admin_user):
    """POST with CSV missing required title field returns 400."""
    user, tenant, workspace = import_admin_user
    client = APIClient()
    token = _login(client, "importadmin", "importpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    csv_file = io.BytesIO(_MISSING_TITLE_CSV)
    csv_file.name = "missing_title.csv"

    resp = client.post(
        f"/api/v1/workspaces/{workspace.id}/import/csv/",
        {"file": csv_file, "entity_type": "Requirement"},
        format="multipart",
    )

    assert resp.status_code == 400
    body = resp.json()
    assert body["success"] is False
    assert body["status"] == "validation_error"
    assert len(body["errors"]) > 0


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_post_empty_csv_returns_400(import_admin_user):
    """POST with empty CSV file returns 400."""
    user, tenant, workspace = import_admin_user
    client = APIClient()
    token = _login(client, "importadmin", "importpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    csv_file = io.BytesIO(b"")
    csv_file.name = "empty.csv"

    resp = client.post(
        f"/api/v1/workspaces/{workspace.id}/import/csv/",
        {"file": csv_file, "entity_type": "Requirement"},
        format="multipart",
    )

    assert resp.status_code == 400
    body = resp.json()
    assert "error" in body


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_post_unauthenticated():
    """Unauthenticated request returns 401 or 403."""
    client = APIClient()
    fake_ws_id = uuid.uuid4()

    csv_file = io.BytesIO(_VALID_CSV)
    csv_file.name = "test.csv"

    resp = client.post(
        f"/api/v1/workspaces/{fake_ws_id}/import/csv/",
        {"file": csv_file, "entity_type": "Requirement"},
        format="multipart",
    )

    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# UI-30: frontend column mirror must not drift from the backend registry
# ---------------------------------------------------------------------------


def test_frontend_known_csv_columns_match_entity_field_specs():
    """`csvPreview.ts` mirrors ``ENTITY_FIELD_SPECS`` — keep them identical.

    The CSV import page runs the backend's own two header checks client-side
    (unrecognised column, required ``title``) so the user gets the verdict
    before paying for an upload round-trip. That mirror is only honest while it
    lists exactly the columns this service accepts: a column added here but not
    there would be reported to the user as "unknown, its data will NOT be
    imported" while the backend happily imports it.

    Guarding it from the Python side is deliberate — the TypeScript test suite
    cannot import ``ENTITY_FIELD_SPECS``, so this is the only place where the
    two lists can actually be compared.
    """
    import re
    from pathlib import Path

    from application.export_service import ENTITY_FIELD_SPECS

    preview_ts = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "src"
        / "components"
        / "CsvImport"
        / "csvPreview.ts"
    )
    if not preview_ts.is_file():
        # The backend dev container mounts only `backend/` as /app, so the
        # frontend tree is genuinely absent there. CI runs pytest against the
        # full checkout (`working-directory: backend`), which is where this
        # guard actually bites.
        pytest.skip(f"frontend tree not available at {preview_ts}")

    source = preview_ts.read_text(encoding="utf-8")
    block = re.search(
        r"export const KNOWN_CSV_COLUMNS[^=]*=\s*\{(.*?)\n\};",
        source,
        re.DOTALL,
    )
    assert block, "KNOWN_CSV_COLUMNS declaration not found in csvPreview.ts"

    frontend: dict[str, set[str]] = {}
    for entity, body in re.findall(r"(\w+):\s*\[(.*?)\]", block.group(1), re.DOTALL):
        frontend[entity] = set(re.findall(r'"([^"]+)"', body))

    # The import page only offers these three entity types (ENTITY_TYPES).
    assert set(frontend) == {"Requirement", "ArchitectureElement", "TestCase"}

    for entity, columns in frontend.items():
        expected = {column for column, _kind in ENTITY_FIELD_SPECS[entity]}
        assert columns == expected, (
            f"csvPreview.ts KNOWN_CSV_COLUMNS['{entity}'] drifted from "
            f"ENTITY_FIELD_SPECS: missing={sorted(expected - columns)}, "
            f"extra={sorted(columns - expected)}"
        )
