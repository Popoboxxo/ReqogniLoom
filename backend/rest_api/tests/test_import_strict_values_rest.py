"""REST status mapping for strict CSV import values (backend review S1-S3).

The service reports every defect of the strict value/workspace handling as a
*domain* outcome, and this suite pins the HTTP contract on top of it:

* one unconvertible cell in an otherwise valid file -> 207 (partial success)
  with a row/field-named ``INVALID_VALUE`` item, never a 500,
* a file whose only rows are unconvertible -> 422, again per row,
* an unknown workspace -> 404 (``NotFoundError``), not a 422 rollback and not
  a 500 ``INTERNAL_SERVER_ERROR``.

A malformed workspace *UUID* cannot reach the view (the URL pattern uses the
``uuid`` converter, so Django answers 404 before dispatch); it is covered at
the service level in ``application/tests/test_import_service_strict_values.py``.
"""
from __future__ import annotations

import io
import uuid

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Requirement, Tenant, User, Workspace

_JWT_OVERRIDES = {
    "AUTH_JWT_SECRET": "test-secret-not-a-real-key",
    "AUTH_JWT_ISSUER": "reqflow",
    "AUTH_JWT_AUDIENCE": "reqflow-api",
    "AUTH_JWT_TTL_SECONDS": 3600,
    "IMPORT_CONTRACT_V2": True,
}

_PASSWORD = "strictpass123"

# Two valid rows, then one row whose ``level`` cell cannot be an integer.
_PARTIAL_CSV = (
    b"title,level\n"
    b"Strict Good One,2\n"
    b"Strict Good Two,3\n"
    b"Strict Bad Row,abc\n"
)

# Every row carries an unconvertible cell.
_ALL_BROKEN_CSV = (
    b"title,suspect\n"
    b"Strict Typo One,ture\n"
    b"Strict Typo Two,maybe\n"
)


@pytest.fixture
def import_admin_user(db):
    """A tenant with one admin user and one workspace."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(
        name=f"STRICT-REST-{suffix}", slug=f"strict-rest-{suffix}", is_active=True
    )
    user = User.objects.create(
        username=f"strict-{suffix}", email=f"strict-{suffix}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="STRICT-REST-WS", preset={"name": "standard"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()

    return user, tenant, workspace


def _client(user: User) -> APIClient:
    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": _PASSWORD},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client


def _upload(client: APIClient, workspace_id, content: bytes):
    csv_file = io.BytesIO(content)
    csv_file.name = "import.csv"
    return client.post(
        f"/api/v1/workspaces/{workspace_id}/import/csv/",
        {"file": csv_file, "entity_type": "Requirement"},
        format="multipart",
    )


def _requirement_titles(tenant_id, workspace_id) -> list[str]:
    set_request_tenant(tenant_id)
    try:
        return sorted(
            Requirement.objects.filter(
                artifact__workspace_id=workspace_id
            ).values_list("title", flat=True)
        )
    finally:
        clear_request_tenant()


@override_settings(**_JWT_OVERRIDES)
def test_bad_cell_in_valid_file_returns_207_with_row_and_field(import_admin_user):
    user, tenant, workspace = import_admin_user
    client = _client(user)

    resp = _upload(client, workspace.id, _PARTIAL_CSV)

    assert resp.status_code == 207, resp.content
    body = resp.json()
    assert body["counts"] == {"succeeded": 2, "skipped": 0, "failed": 1, "total": 3}

    failed = [item for item in body["items"] if item["status"] == "failed"]
    assert len(failed) == 1
    assert failed[0]["row"] == 4
    assert failed[0]["cause"]["code"] == "INVALID_VALUE"
    assert "level" in failed[0]["cause"]["message"]

    # The two valid rows really landed; the bad one did not.
    assert _requirement_titles(tenant.id, workspace.id) == [
        "Strict Good One",
        "Strict Good Two",
    ]


@override_settings(**_JWT_OVERRIDES)
def test_all_rows_unconvertible_returns_422_not_500(import_admin_user):
    user, tenant, workspace = import_admin_user
    client = _client(user)

    resp = _upload(client, workspace.id, _ALL_BROKEN_CSV)

    assert resp.status_code == 422, resp.content
    body = resp.json()
    assert body["success"] is False
    assert body["counts"]["failed"] == 2
    codes = {item["cause"]["code"] for item in body["items"]}
    assert codes == {"INVALID_VALUE"}
    assert _requirement_titles(tenant.id, workspace.id) == []


@override_settings(**_JWT_OVERRIDES)
def test_unknown_workspace_returns_404(import_admin_user):
    user, _tenant, _workspace = import_admin_user
    client = _client(user)

    resp = _upload(client, uuid.uuid4(), _PARTIAL_CSV)

    assert resp.status_code == 404, resp.content
    body = resp.json()
    assert body.get("error", {}).get("code") == "NOT_FOUND" or "not found" in str(
        body
    ).lower()
    # No persistence rollback / internal-error envelope.
    assert "PERSISTENCE_ERROR" not in resp.content.decode()
    assert "INTERNAL_SERVER_ERROR" not in resp.content.decode()
