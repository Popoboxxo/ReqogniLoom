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
                artifact__workspace=workspace_b, artifact__reqif_uid="NEED-IMP-001"
            ).count()
            == 1
        )
        assert (
            Requirement.objects.filter(
                artifact__workspace=workspace_b, artifact__reqif_uid="REQ-IMP-001"
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
    # ADR-014 §3: identical content on re-import is an idempotent skip.
    assert body["needs"]["created"] == 0
    assert body["needs"]["updated"] == 0
    assert body["needs"]["skipped"] == 1
    assert body["requirements"]["created"] == 0
    assert body["requirements"]["updated"] == 0
    assert body["requirements"]["skipped"] == 1
    assert body["success"] is True
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
def test_reqif_import_malformed_xml_returns_422_parse_error(reqif_import_admin_user):
    """ADR-014 §2 / REQ-L2-RQ-001 AC5: an invalid .reqif file is a file-level
    PARSE_ERROR answered with 422 + structured details (not a 400)."""
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

    assert resp.status_code == 422
    body = resp.json()
    assert body["success"] is False
    assert body["contract"] == "v2"
    assert body["counts"]["failed"] == 1
    assert body["items"][0]["cause"]["code"] == "PARSE_ERROR"


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


# ---------------------------------------------------------------------------
# ADR-014 contract v2: 207/422 mapping, skipped-only, Idempotency-Key
# ---------------------------------------------------------------------------


def _upload(client: APIClient, workspace_id, content: bytes, **extra):
    reqif_file = io.BytesIO(content)
    reqif_file.name = "export.reqif"
    return client.post(
        f"/api/v1/workspaces/{workspace_id}/import/reqif/",
        {"file": reqif_file},
        format="multipart",
        **extra,
    )


def _counts_in_workspace(tenant, workspace_id) -> tuple:
    set_request_tenant(tenant.id)
    try:
        return (
            StakeholderNeed.objects.filter(artifact__workspace_id=workspace_id).count(),
            Requirement.objects.filter(artifact__workspace_id=workspace_id).count(),
        )
    finally:
        clear_request_tenant()


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_partial_failure_returns_207(reqif_import_admin_user):
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    content = _export_reqif(client, workspace_a.id)
    mutated = content.replace(
        b'THE-VALUE="REST Import Req Alpha"',
        b'THE-VALUE="' + b"X" * 501 + b'"',
        1,
    )
    assert mutated != content

    resp = _upload(client, workspace_b.id, mutated)

    assert resp.status_code == 207
    body = resp.json()
    assert body["success"] is False
    assert body["contract"] == "v2"
    assert body["counts"]["failed"] == 1
    assert body["counts"]["succeeded"] >= 1
    failed = [i for i in body["items"] if i["status"] == "failed"]
    assert failed and failed[0]["cause"]["code"] == "INVALID_VALUE"
    # The failing object was rolled back to its savepoint; the valid need stays.
    need_count, req_count = _counts_in_workspace(tenant, workspace_b.id)
    assert need_count == 1
    assert req_count == 0


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_total_failure_returns_422(reqif_import_admin_user):
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    content = _export_reqif(client, workspace_a.id)
    long_title = 'THE-VALUE="' + "X" * 501 + '"'
    mutated = content.replace(b'THE-VALUE="REST Import Need Alpha"', long_title.encode())
    mutated = mutated.replace(b'THE-VALUE="REST Import Req Alpha"', long_title.encode())
    assert mutated != content

    resp = _upload(client, workspace_b.id, mutated)

    assert resp.status_code == 422
    body = resp.json()
    assert body["success"] is False
    assert body["counts"]["succeeded"] == 0
    assert body["counts"]["failed"] >= 1
    assert body["items"]  # errors/items never empty on total failure


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_skipped_only_returns_200_success(reqif_import_admin_user):
    """A second identical upload is a skipped-only no-op: success with 200."""
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    content = _export_reqif(client, workspace_a.id)
    assert _upload(client, workspace_b.id, content).status_code == 200

    resp = _upload(client, workspace_b.id, content)

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["counts"]["failed"] == 0
    assert body["counts"]["succeeded"] == 0
    assert body["counts"]["skipped"] >= 2


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_idempotency_key_replay_does_not_write(reqif_import_admin_user):
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    content = _export_reqif(client, workspace_a.id)

    first = _upload(
        client, workspace_b.id, content, HTTP_IDEMPOTENCY_KEY="reqif-idem-1"
    )
    assert first.status_code == 200
    assert first.json()["idempotent_replay"] is False
    before = _counts_in_workspace(tenant, workspace_b.id)

    replay = _upload(
        client, workspace_b.id, content, HTTP_IDEMPOTENCY_KEY="reqif-idem-1"
    )
    assert replay.status_code == 200
    body = replay.json()
    assert body["idempotent_replay"] is True
    assert body["success"] is True
    after = _counts_in_workspace(tenant, workspace_b.id)
    assert after == before  # no second write effect


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_idempotency_key_reused_with_different_payload_returns_409(
    reqif_import_admin_user,
):
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    content = _export_reqif(client, workspace_a.id)
    assert (
        _upload(client, workspace_b.id, content, HTTP_IDEMPOTENCY_KEY="reqif-idem-2")
        .status_code
        == 200
    )

    other = content.replace(
        b'THE-VALUE="REST Import Req Alpha"',
        b'THE-VALUE="REST Import Req Beta"',
        1,
    )
    assert other != content
    resp = _upload(
        client, workspace_b.id, other, HTTP_IDEMPOTENCY_KEY="reqif-idem-2"
    )

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_idempotency_key_too_long_returns_400(reqif_import_admin_user):
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    content = _export_reqif(client, workspace_a.id)
    resp = _upload(
        client, workspace_b.id, content, HTTP_IDEMPOTENCY_KEY="k" * 256
    )
    assert resp.status_code == 400


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reqif_import_legacy_fallback_when_contract_v2_disabled(
    reqif_import_admin_user,
):
    """IMPORT_CONTRACT_V2=false restores the pre-ADR response (ADR-014 §5)."""
    user, tenant, workspace_a, workspace_b = reqif_import_admin_user
    client = APIClient()
    token = _login(client, "reqifimportadmin", "reqifpass123")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    content = _export_reqif(client, workspace_a.id)
    with override_settings(IMPORT_CONTRACT_V2=False):
        resp = _upload(client, workspace_b.id, content)

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "contract" not in body
    assert "counts" not in body
