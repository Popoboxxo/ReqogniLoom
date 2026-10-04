"""INT-04 hardening tests for the CSV import REST endpoint.

Covers:
  * UTF-8 BOM upload (Finding 083),
  * natural-key dedupe across repeated uploads (Finding 072),
  * honest error reporting and the ADR-014 contract-v2 envelope + replay.
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

_SECRET = "test-secret-not-a-real-key"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)

_V2_OVERRIDES = dict(_JWT_OVERRIDES, IMPORT_CONTRACT_V2=True)

_VALID_CSV = (
    b"title,description,category,status\n"
    b"INT04 Req One,First,functional,draft\n"
    b"INT04 Req Two,Second,non-functional,draft\n"
)

_BOM_CSV = (
    b"\xef\xbb\xbftitle,description,category,status\n"
    b"INT04 BOM Req,BOM handled,functional,draft\n"
)

_MISSING_TITLE_CSV = b"title,description\n,No title here\n"


@pytest.fixture
def import_admin_user(db):
    tenant = Tenant.objects.create(
        name="INT04-REST-T", slug=f"int04-rest-{uuid.uuid4().hex[:8]}", is_active=True
    )
    user = User.objects.create(
        username="int04admin", email="int04admin@t.test", tenant=tenant
    )
    user.set_password("int04pass123")
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="INT04-REST-WS", preset={"name": "standard"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()

    return user, tenant, workspace


def _login(client: APIClient) -> None:
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": "int04admin", "password": "int04pass123"},
        format="json",
    )
    assert resp.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")


def _upload(client, workspace_id, content: bytes, **extra):
    csv_file = io.BytesIO(content)
    csv_file.name = "import.csv"
    return client.post(
        f"/api/v1/workspaces/{workspace_id}/import/csv/",
        {"file": csv_file, "entity_type": "Requirement"},
        format="multipart",
        **extra,
    )


def _requirement_count(tenant_id, workspace_id) -> int:
    set_request_tenant(tenant_id)
    try:
        return Requirement.objects.filter(artifact__workspace_id=workspace_id).count()
    finally:
        clear_request_tenant()


# ---------- BOM (Finding 083) ----------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_bom_upload_imports_correctly(import_admin_user):
    _user, tenant, workspace = import_admin_user
    client = APIClient()
    _login(client)

    resp = _upload(client, workspace.id, _BOM_CSV)

    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    assert body["imported_count"] == 1
    assert _requirement_count(tenant.id, workspace.id) == 1


# ---------- Dedupe (Finding 072) ----------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_importing_same_file_twice_creates_no_duplicates(import_admin_user):
    _user, tenant, workspace = import_admin_user
    client = APIClient()
    _login(client)

    first = _upload(client, workspace.id, _VALID_CSV)
    assert first.status_code == 201
    assert first.json()["imported_count"] == 2

    second = _upload(client, workspace.id, _VALID_CSV)
    assert second.status_code == 201
    body = second.json()
    assert body["success"] is True
    assert body["imported_count"] == 0
    assert body["skipped_count"] == 2

    assert _requirement_count(tenant.id, workspace.id) == 2


# ---------- Legacy contract (flag off) ----------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_legacy_response_shape_unchanged(import_admin_user):
    _user, _tenant, workspace = import_admin_user
    client = APIClient()
    _login(client)

    body = _upload(client, workspace.id, _VALID_CSV).json()

    assert "contract" not in body
    assert body["errors"] == []
    assert body["status"] == "ok"


# ---------- Contract v2: envelope, status matrix, replay ----------


@override_settings(**_V2_OVERRIDES)
@pytest.mark.django_db
def test_v2_envelope_and_skipped_only_status(import_admin_user):
    _user, tenant, workspace = import_admin_user
    client = APIClient()
    _login(client)

    first = _upload(client, workspace.id, _VALID_CSV)
    assert first.status_code == 201
    first_body = first.json()
    assert first_body["contract"] == "v2"
    assert first_body["counts"] == {
        "succeeded": 2,
        "skipped": 0,
        "failed": 0,
        "total": 2,
    }
    assert first_body["idempotent_replay"] is False

    # A pure duplicate import writes nothing and is an HTTP 200 success.
    second = _upload(client, workspace.id, _VALID_CSV)
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["success"] is True
    assert second_body["counts"]["succeeded"] == 0
    assert second_body["counts"]["skipped"] == 2
    assert second_body["counts"]["failed"] == 0
    assert {i["cause"]["code"] for i in second_body["items"]} == {"DUPLICATE"}
    assert _requirement_count(tenant.id, workspace.id) == 2


@override_settings(**_V2_OVERRIDES)
@pytest.mark.django_db
def test_v2_validation_failure_is_422_with_items(import_admin_user):
    _user, _tenant, workspace = import_admin_user
    client = APIClient()
    _login(client)

    resp = _upload(client, workspace.id, _MISSING_TITLE_CSV)

    assert resp.status_code == 422
    body = resp.json()
    assert body["success"] is False
    assert body["counts"]["failed"] >= 1
    assert len(body["items"]) >= 1
    assert body["items"][0]["status"] == "failed"


@override_settings(**_V2_OVERRIDES)
@pytest.mark.django_db
def test_v2_idempotency_key_replay_has_no_second_write(import_admin_user):
    _user, tenant, workspace = import_admin_user
    client = APIClient()
    _login(client)

    first = _upload(
        client, workspace.id, _VALID_CSV, HTTP_IDEMPOTENCY_KEY="int04-key-1"
    )
    assert first.status_code == 201
    first_body = first.json()
    assert first_body["idempotent_replay"] is False
    assert _requirement_count(tenant.id, workspace.id) == 2

    replay = _upload(
        client, workspace.id, _VALID_CSV, HTTP_IDEMPOTENCY_KEY="int04-key-1"
    )
    assert replay.status_code == 201
    replay_body = replay.json()
    assert replay_body["idempotent_replay"] is True
    assert replay_body["counts"] == first_body["counts"]

    # The replay must not have written a second time.
    assert _requirement_count(tenant.id, workspace.id) == 2
