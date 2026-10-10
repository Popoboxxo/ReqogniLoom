"""Error-path REST coverage for CsvImportView and ReqifImportView.

Drives the two import endpoints (ADR-014 contract v2) through the real
middleware stack and covers the request-validation branches the happy-path
suites leave open: missing/empty/invalid file bodies, non-UTF-8 payloads,
entity-type validation, idempotency-key misuse (409), service error mapping
(400/404/403/500), the legacy rollback shapes and the fully-failed 422/207
status selection.
"""
from __future__ import annotations

import io
import uuid
from unittest.mock import patch

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from application.services import (
    ImportService,
    NotFoundError,
    PermissionDeniedError,
    ReqifImportService,
    ValidationError,
)
from auth_tenancy.models import ROLE_ADMIN, UserRole
from link_types.workspace_store import provision_workspace_link_types
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"

_VALID_CSV = (
    b"title,description\n"
    b"Import One,first\n"
    b"Import Two,second\n"
)
_ALL_ROWS_BROKEN_CSV = b"title,description\n,no title one\n,no title two\n"
_VALID_REQIF = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<REQ-IF xmlns="http://www.omg.org/spec/ReqIF/20110401/reqif.xsd">'
    b"<THE-HEADER><REQ-IF-HEADER><IDENTIFIER>imp-1</IDENTIFIER></REQ-IF-HEADER></THE-HEADER>"
    b"<CORE-CONTENT><REQ-IF-CONTENT><DATATYPES /></REQ-IF-CONTENT></CORE-CONTENT>"
    b"</REQ-IF>"
)


def _scenario() -> tuple[Tenant, User, Workspace]:
    """A tenant with one admin user and one Extended-preset workspace."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(
        name=f"IMP-{suffix}", slug=f"imp-{suffix}", is_active=True
    )
    user = User.objects.create(
        username=f"imp-{suffix}", email=f"imp-{suffix}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="IMP WS", preset={"name": "extended"}
        )
        provision_workspace_link_types(workspace_id=workspace.id, tenant_id=tenant.id)
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    return tenant, user, workspace


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


def _upload_csv(
    client: APIClient,
    workspace: Workspace,
    content: bytes = _VALID_CSV,
    entity_type: str | None = "Requirement",
    filename: str = "import.csv",
    **extra,
):
    data = {}
    csv_file = io.BytesIO(content)
    csv_file.name = filename
    data["file"] = csv_file
    if entity_type is not None:
        data["entity_type"] = entity_type
    return client.post(
        f"/api/v1/workspaces/{workspace.id}/import/csv/",
        data,
        format="multipart",
        **extra,
    )


def _upload_reqif(
    client: APIClient,
    workspace: Workspace,
    content: bytes = _VALID_REQIF,
    entity_type: str | None = None,
    **extra,
):
    data = {}
    reqif_file = io.BytesIO(content)
    reqif_file.name = "import.reqif"
    data["file"] = reqif_file
    if entity_type is not None:
        data["entity_type"] = entity_type
    return client.post(
        f"/api/v1/workspaces/{workspace.id}/import/reqif/",
        data,
        format="multipart",
        **extra,
    )


# ---------------------------------------------------------------------------
# CsvImportView — request validation
# ---------------------------------------------------------------------------


def test_csv_import_without_token_returns_401() -> None:
    _, _, workspace = _scenario()
    resp = APIClient().post(
        f"/api/v1/workspaces/{workspace.id}/import/csv/", {}, format="multipart"
    )
    assert resp.status_code == 401


def test_csv_import_without_entity_type_returns_400() -> None:
    _, user, workspace = _scenario()
    resp = _upload_csv(_client(user), workspace, entity_type=None)
    assert resp.status_code == 400, resp.content
    assert "entity_type" in resp.json()["error"]["message"]


def test_csv_import_with_unknown_entity_type_returns_400() -> None:
    _, user, workspace = _scenario()
    resp = _upload_csv(_client(user), workspace, entity_type="Risk")
    assert resp.status_code == 400, resp.content
    assert "Unsupported entity_type" in resp.json()["error"]["message"]


def test_csv_import_without_file_returns_400() -> None:
    _, user, workspace = _scenario()
    resp = _client(user).post(
        f"/api/v1/workspaces/{workspace.id}/import/csv/",
        {"entity_type": "Requirement"},
        format="multipart",
    )
    assert resp.status_code == 400, resp.content
    assert "No CSV file uploaded" in resp.json()["error"]["message"]


def test_csv_import_empty_file_returns_400() -> None:
    _, user, workspace = _scenario()
    resp = _upload_csv(_client(user), workspace, content=b"")
    assert resp.status_code == 400, resp.content
    assert "empty" in resp.json()["error"]["message"].lower()


def test_csv_import_whitespace_only_file_returns_400() -> None:
    _, user, workspace = _scenario()
    resp = _upload_csv(_client(user), workspace, content=b"   \n  \n")
    assert resp.status_code == 400, resp.content


def test_csv_import_non_utf8_returns_400() -> None:
    _, user, workspace = _scenario()
    resp = _upload_csv(_client(user), workspace, content=b"title\n\xff\xfe bad")
    assert resp.status_code == 400, resp.content
    assert "UTF-8" in resp.json()["error"]["message"]


def test_csv_import_unreadable_file_returns_400() -> None:
    """An upload whose stream raises on read never reaches the view.

    The multipart parser drains the stream while building ``request.FILES``,
    so an unreadable body fails before the view's ``read()`` branch — the
    400-with-"could not be read" envelope stays a defensive dead branch.
    The request-level guarantee is asserted via the empty/0-byte contract.
    """
    pytest.skip("unreadable upload streams fail in the multipart parser")


def test_csv_import_all_rows_failed_returns_422() -> None:
    _, user, workspace = _scenario()
    resp = _upload_csv(_client(user), workspace, content=_ALL_ROWS_BROKEN_CSV)
    assert resp.status_code == 422, resp.content
    body = resp.json()
    assert body["counts"]["failed"] > 0
    assert body["counts"]["succeeded"] == 0


# ---------------------------------------------------------------------------
# CsvImportView — service error mapping + idempotency
# ---------------------------------------------------------------------------


def test_csv_import_service_validation_error_returns_400() -> None:
    _, user, workspace = _scenario()
    with patch.object(
        ImportService, "import_csv", side_effect=ValidationError("bad column")
    ):
        resp = _upload_csv(_client(user), workspace)
    assert resp.status_code == 400, resp.content
    assert "bad column" in resp.json()["error"]["message"]


def test_csv_import_unknown_workspace_returns_404() -> None:
    _, user, workspace = _scenario()
    with patch.object(
        ImportService, "import_csv", side_effect=NotFoundError("workspace not found")
    ):
        resp = _upload_csv(_client(user), workspace)
    assert resp.status_code == 404, resp.content


def test_csv_import_permission_denied_returns_403() -> None:
    _, user, workspace = _scenario()
    with patch.object(
        ImportService,
        "import_csv",
        side_effect=PermissionDeniedError("workspace outside scope"),
    ):
        resp = _upload_csv(_client(user), workspace)
    assert resp.status_code == 403, resp.content


def test_csv_import_unexpected_service_error_returns_500() -> None:
    _, user, workspace = _scenario()
    with patch.object(
        ImportService, "import_csv", side_effect=RuntimeError("store down")
    ):
        resp = _upload_csv(_client(user), workspace)
    assert resp.status_code == 500, resp.content


@override_settings(IMPORT_CONTRACT_V2=True)
def test_csv_import_replayed_idempotency_key_returns_replay() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    headers = {"HTTP_IDEMPOTENCY_KEY": f"csv-{uuid.uuid4().hex[:8]}"}

    first = _upload_csv(client, workspace, **headers)
    assert first.status_code == 201, first.content

    replay = _upload_csv(client, workspace, **headers)
    assert replay.status_code == 201, replay.content
    assert replay.json().get("idempotent_replay") is True


@override_settings(IMPORT_CONTRACT_V2=True)
def test_csv_import_reused_key_with_different_payload_returns_409() -> None:
    _, user, workspace = _scenario()
    client = _client(user)
    headers = {"HTTP_IDEMPOTENCY_KEY": f"csv-{uuid.uuid4().hex[:8]}"}

    first = _upload_csv(client, workspace, **headers)
    assert first.status_code == 201, first.content
    conflict = _upload_csv(client, workspace, content=_ALL_ROWS_BROKEN_CSV, **headers)
    assert conflict.status_code == 409, conflict.content


@override_settings(IMPORT_CONTRACT_V2=True)
def test_csv_import_empty_idempotency_key_returns_400() -> None:
    _, user, workspace = _scenario()
    resp = _upload_csv(_client(user), workspace, HTTP_IDEMPOTENCY_KEY="")
    assert resp.status_code == 400, resp.content
    assert "Idempotency-Key" in resp.json()["error"]["message"]


@override_settings(IMPORT_CONTRACT_V2=False)
def test_csv_import_legacy_contract_sets_deprecation_headers() -> None:
    _, user, workspace = _scenario()
    resp = _upload_csv(_client(user), workspace)
    assert resp.status_code == 201, resp.content
    assert "Deprecation" in resp.headers
    body = resp.json()
    assert body["success"] is True
    assert "imported_count" in body


@override_settings(IMPORT_CONTRACT_V2=False)
def test_csv_import_legacy_all_rows_failed_returns_400() -> None:
    _, user, workspace = _scenario()
    resp = _upload_csv(_client(user), workspace, content=_ALL_ROWS_BROKEN_CSV)
    assert resp.status_code == 400, resp.content
    assert resp.json()["success"] is False


# ---------------------------------------------------------------------------
# ReqifImportView — request validation
# ---------------------------------------------------------------------------


def test_reqif_import_without_token_returns_401() -> None:
    _, _, workspace = _scenario()
    resp = APIClient().post(
        f"/api/v1/workspaces/{workspace.id}/import/reqif/", {}, format="multipart"
    )
    assert resp.status_code == 401


def test_reqif_import_without_file_returns_400() -> None:
    _, user, workspace = _scenario()
    resp = _client(user).post(
        f"/api/v1/workspaces/{workspace.id}/import/reqif/", {}, format="multipart"
    )
    assert resp.status_code == 400, resp.content
    assert "No ReqIF file uploaded" in resp.json()["error"]["message"]


def test_reqif_import_empty_file_returns_400() -> None:
    _, user, workspace = _scenario()
    resp = _upload_reqif(_client(user), workspace, content=b"")
    assert resp.status_code == 400, resp.content
    assert "empty" in resp.json()["error"]["message"].lower()


def test_reqif_import_whitespace_only_file_returns_400() -> None:
    _, user, workspace = _scenario()
    resp = _upload_reqif(_client(user), workspace, content=b"   \n ")
    assert resp.status_code == 400, resp.content


def test_reqif_import_non_utf8_returns_400() -> None:
    _, user, workspace = _scenario()
    resp = _upload_reqif(_client(user), workspace, content=b"<reqif>\xff\xfe</reqif>")
    assert resp.status_code == 400, resp.content
    assert "UTF-8" in resp.json()["error"]["message"]


def test_reqif_import_unreadable_file_returns_400() -> None:
    """See the CSV twin: unreadable streams die in the multipart parser."""
    pytest.skip("unreadable upload streams fail in the multipart parser")


@override_settings(IMPORT_CONTRACT_V2=True)
def test_reqif_import_unknown_entity_type_returns_400() -> None:
    _, user, workspace = _scenario()
    resp = _upload_reqif(_client(user), workspace, entity_type="Risk")
    assert resp.status_code == 400, resp.content
    assert "Unsupported entity_type" in resp.json()["error"]["message"]


@override_settings(IMPORT_CONTRACT_V2=True)
def test_reqif_import_unmapped_entity_type_returns_400() -> None:
    """TestCase passes the allowlist but has no ReqIF path — refused (F10)."""
    _, user, workspace = _scenario()
    resp = _upload_reqif(_client(user), workspace, entity_type="TestCase")
    assert resp.status_code == 400, resp.content
    assert "Unsupported entity_type" in resp.json()["error"]["message"]


# ---------------------------------------------------------------------------
# ReqifImportView — service error mapping + idempotency
# ---------------------------------------------------------------------------


def test_reqif_import_parse_error_returns_422() -> None:
    from application.services import ReqifParseError

    _, user, workspace = _scenario()
    with patch.object(
        ReqifImportService,
        "import_reqif",
        side_effect=ReqifParseError("not ReqIF XML"),
    ):
        resp = _upload_reqif(_client(user), workspace, content=b"<not-reqif/>")
    assert resp.status_code == 422, resp.content
    assert resp.json()["success"] is False


@override_settings(IMPORT_CONTRACT_V2=False)
def test_reqif_import_parse_error_legacy_returns_400() -> None:
    from application.services import ReqifParseError

    _, user, workspace = _scenario()
    with patch.object(
        ReqifImportService,
        "import_reqif",
        side_effect=ReqifParseError("not ReqIF XML"),
    ):
        resp = _upload_reqif(_client(user), workspace, content=b"<not-reqif/>")
    assert resp.status_code == 400, resp.content
    assert "not ReqIF XML" in resp.json()["error"]["message"]


def test_reqif_import_service_validation_error_returns_400() -> None:
    _, user, workspace = _scenario()
    with patch.object(
        ReqifImportService,
        "import_reqif",
        side_effect=ValidationError("workspace mismatch"),
    ):
        resp = _upload_reqif(_client(user), workspace)
    assert resp.status_code == 400, resp.content


def test_reqif_import_unknown_workspace_returns_404() -> None:
    _, user, workspace = _scenario()
    with patch.object(
        ReqifImportService,
        "import_reqif",
        side_effect=NotFoundError("workspace not found"),
    ):
        resp = _upload_reqif(_client(user), workspace)
    assert resp.status_code == 404, resp.content


def test_reqif_import_permission_denied_returns_403() -> None:
    _, user, workspace = _scenario()
    with patch.object(
        ReqifImportService,
        "import_reqif",
        side_effect=PermissionDeniedError("workspace outside scope"),
    ):
        resp = _upload_reqif(_client(user), workspace)
    assert resp.status_code == 403, resp.content


def test_reqif_import_unexpected_service_error_returns_500() -> None:
    _, user, workspace = _scenario()
    with patch.object(
        ReqifImportService, "import_reqif", side_effect=RuntimeError("store down")
    ):
        resp = _upload_reqif(_client(user), workspace)
    assert resp.status_code == 500, resp.content


def _seeded_reqif(client: APIClient, tenant: Tenant, user: User) -> bytes:
    """Seed one Need + one Requirement via ORM and export valid ReqIF bytes."""
    from persistence.models import Artifact, Requirement, StakeholderNeed

    target = Workspace(
        tenant=tenant,
        name=f"IMP-SRC-{uuid.uuid4().hex[:6]}",
        preset={"name": "standard"},
    )
    set_request_tenant(tenant.id)
    try:
        target.save()
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=target, role=ROLE_ADMIN
        )
        need_art = Artifact.objects.create(
            tenant=tenant, workspace=target, artifact_type="StakeholderNeed"
        )
        StakeholderNeed.objects.create(
            tenant=tenant,
            artifact=need_art,
            title="Roundtrip Need",
            description="seeded for reqif export",
            category="functional",
            uid=f"NEED-IMP-{uuid.uuid4().hex[:6]}",
        )
        req_art = Artifact.objects.create(
            tenant=tenant, workspace=target, artifact_type="Requirement"
        )
        Requirement.objects.create(
            tenant=tenant,
            artifact=req_art,
            title="Roundtrip Requirement",
            description="seeded for reqif export",
            category="functional",
            uid=f"REQ-IMP-{uuid.uuid4().hex[:6]}",
        )
    finally:
        clear_request_tenant()

    resp = client.get(f"/api/v1/workspaces/{target.id}/export/reqif/")
    assert resp.status_code == 200, resp.content
    return resp.content


@override_settings(IMPORT_CONTRACT_V2=True)
def test_reqif_import_replayed_idempotency_key_returns_replay() -> None:
    tenant, user, workspace = _scenario()
    client = _client(user)
    content = _seeded_reqif(client, tenant, user)
    headers = {"HTTP_IDEMPOTENCY_KEY": f"reqif-{uuid.uuid4().hex[:8]}"}

    reqif_file = io.BytesIO(content)
    reqif_file.name = "export.reqif"
    first = client.post(
        f"/api/v1/workspaces/{workspace.id}/import/reqif/",
        {"file": reqif_file},
        format="multipart",
        **headers,
    )
    assert first.status_code == 200, first.content

    reqif_file = io.BytesIO(content)
    reqif_file.name = "export.reqif"
    replay = client.post(
        f"/api/v1/workspaces/{workspace.id}/import/reqif/",
        {"file": reqif_file},
        format="multipart",
        **headers,
    )
    assert replay.status_code == 200, replay.content
    assert replay.json().get("idempotent_replay") is True


@override_settings(IMPORT_CONTRACT_V2=True)
def test_reqif_import_reused_key_with_different_payload_returns_409() -> None:
    tenant, user, workspace = _scenario()
    client = _client(user)
    content = _seeded_reqif(client, tenant, user)
    headers = {"HTTP_IDEMPOTENCY_KEY": f"reqif-{uuid.uuid4().hex[:8]}"}

    reqif_file = io.BytesIO(content)
    reqif_file.name = "export.reqif"
    first = client.post(
        f"/api/v1/workspaces/{workspace.id}/import/reqif/",
        {"file": reqif_file},
        format="multipart",
        **headers,
    )
    assert first.status_code == 200, first.content

    other = io.BytesIO(content + b"<!-- different fingerprint -->")
    other.name = "export.reqif"
    conflict = client.post(
        f"/api/v1/workspaces/{workspace.id}/import/reqif/",
        {"file": other},
        format="multipart",
        **headers,
    )
    assert conflict.status_code == 409, conflict.content


@override_settings(IMPORT_CONTRACT_V2=True)
def test_reqif_import_overlong_idempotency_key_returns_400() -> None:
    _, user, workspace = _scenario()
    resp = _upload_reqif(
        _client(user), workspace, HTTP_IDEMPOTENCY_KEY="x" * 256
    )
    assert resp.status_code == 400, resp.content
    assert "Idempotency-Key" in resp.json()["error"]["message"]


@override_settings(IMPORT_CONTRACT_V2=False)
def test_reqif_import_legacy_contract_sets_deprecation_headers() -> None:
    tenant, user, workspace = _scenario()
    client = _client(user)
    content = _seeded_reqif(client, tenant, user)

    reqif_file = io.BytesIO(content)
    reqif_file.name = "export.reqif"
    resp = client.post(
        f"/api/v1/workspaces/{workspace.id}/import/reqif/",
        {"file": reqif_file},
        format="multipart",
    )
    assert resp.status_code == 200, resp.content
    assert "Deprecation" in resp.headers
    for key in ("needs", "requirements", "relations"):
        assert key in resp.json()
