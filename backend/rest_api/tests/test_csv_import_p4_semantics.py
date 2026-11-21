"""P4 import-semantics tests at the REST seam (D2/D5 + admin gate).

The service-level contract is pinned in ``application/tests/test_import_p4_semantics.py``.
This module verifies that the four new query parameters are actually wired
through ``views_io.CsvImportView.post``:

* ``dry_run`` — no rows are persisted;
* ``conflict_policy`` — ``update`` is an admin-only opt-in;
* ``reconcile_status`` — admin-only, soft-marks absent rows;
* the default ``version-guard`` path stays available to editors.

Most tests are pinned to the legacy response envelope
(``IMPORT_CONTRACT_V2=False``); the request handling and admin gate are
identical in both envelope modes. A separate regression test covers
``IMPORT_CONTRACT_V2=True`` to ensure the three new query parameters are
assigned before they are folded into the idempotency fingerprint.
"""
from __future__ import annotations

import io
import uuid

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, Tenant, User, Workspace

pytestmark = pytest.mark.django_db

_LEGACY = override_settings(
    AUTH_JWT_SECRET="p4-rest-secret",
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
    IMPORT_CONTRACT_V2=False,
)


@pytest.fixture
def env():
    tenant = Tenant.objects.create(
        name="P4REST-T", slug=f"p4rest-{uuid.uuid4().hex[:8]}", is_active=True
    )
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="P4REST WS", preset={"name": "standard"}
        )

        admin = User.objects.create(
            username="p4admin", email="p4admin@t.test", tenant=tenant
        )
        admin.set_password("p4pass123")
        admin.save(update_fields=["password"])
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )

        editor = User.objects.create(
            username="p4editor", email="p4editor@t.test", tenant=tenant
        )
        editor.set_password("p4pass123")
        editor.save(update_fields=["password"])
        UserRole.objects.create(
            tenant=tenant, user=editor, workspace=workspace, role=ROLE_EDITOR
        )
    finally:
        clear_request_tenant()

    return {"tenant": tenant, "workspace": workspace}


def _client(env, *, username="p4admin") -> APIClient:
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": username, "password": "p4pass123"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


def _upload(client, workspace_id, rows, *, query=""):
    csv_file = io.BytesIO(rows)
    csv_file.name = "import.csv"
    url = f"/api/v1/workspaces/{workspace_id}/import/csv/"
    return client.post(
        f"{url}?{query}" if query else url,
        {"file": csv_file, "entity_type": "Requirement"},
        format="multipart",
    )


def _seed(env, *, title, uid, version=1):
    set_request_tenant(env["tenant"].id)
    try:
        artifact = Artifact.objects.create(
            tenant=env["tenant"],
            workspace=env["workspace"],
            artifact_type="Requirement",
        )
        return Requirement.objects.create(
            tenant=env["tenant"],
            artifact=artifact,
            title=title,
            description="seeded",
            category="functional",
            type="SyReq",
            level=1,
            uid=uid,
            version=version,
        )
    finally:
        clear_request_tenant()


def _count(env, uid):
    set_request_tenant(env["tenant"].id)
    try:
        return Requirement.objects.filter(
            uid=uid, artifact__workspace=env["workspace"]
        ).count()
    finally:
        clear_request_tenant()


@_LEGACY
def test_dry_run_param_does_not_persist(env):
    client = _client(env)
    resp = _upload(
        client,
        env["workspace"].id,
        b"uid,title,description\nREQ-P4R-DRY,Dry Row,body\n",
        query="dry_run=true",
    )

    assert resp.status_code in (200, 201), resp.content
    assert _count(env, "REQ-P4R-DRY") == 0


@_LEGACY
def test_editor_forbidden_for_update_policy(env):
    client = _client(env, username="p4editor")
    resp = _upload(
        client,
        env["workspace"].id,
        b"uid,title,description\nREQ-P4R-UPD,New,body\n",
        query="conflict_policy=update",
    )

    assert resp.status_code == 403, resp.content
    assert _count(env, "REQ-P4R-UPD") == 0


@_LEGACY
def test_editor_forbidden_for_reconcile_status(env):
    client = _client(env, username="p4editor")
    resp = _upload(
        client,
        env["workspace"].id,
        b"uid,title,description\nREQ-P4R-REC,New,body\n",
        query="reconcile_status=true",
    )

    assert resp.status_code == 403, resp.content


@_LEGACY
def test_editor_allowed_for_default_version_guard(env):
    client = _client(env, username="p4editor")
    resp = _upload(
        client,
        env["workspace"].id,
        b"uid,title,description\nREQ-P4R-VG,New,body\n",
    )

    assert resp.status_code in (200, 201), resp.content
    assert _count(env, "REQ-P4R-VG") == 1


@_LEGACY
def test_admin_can_use_update_policy(env):
    _seed(env, title="Old", uid="REQ-P4R-ADMUPD", version=1)
    client = _client(env)

    resp = _upload(
        client,
        env["workspace"].id,
        b"uid,title,description,version\nREQ-P4R-ADMUPD,New,body,8\n",
        query="conflict_policy=update",
    )

    assert resp.status_code in (200, 201), resp.content
    set_request_tenant(env["tenant"].id)
    try:
        stored = Requirement.objects.get(
            uid="REQ-P4R-ADMUPD", artifact__workspace=env["workspace"]
        )
        assert stored.title == "New"
    finally:
        clear_request_tenant()


@_LEGACY
def test_admin_can_use_reconcile_status(env):
    _seed(env, title="Keep", uid="REQ-P4R-KEEP")
    _seed(env, title="Gone", uid="REQ-P4R-GONE")
    client = _client(env)

    resp = _upload(
        client,
        env["workspace"].id,
        b"uid,title,description\nREQ-P4R-KEEP,Keep,kept\n",
        query="reconcile_status=true",
    )

    assert resp.status_code in (200, 201), resp.content
    set_request_tenant(env["tenant"].id)
    try:
        gone = Requirement.objects.get(
            uid="REQ-P4R-GONE", artifact__workspace=env["workspace"]
        )
        assert dict(gone.artifact.custom_fields or {}).get("not_in_source") is True
    finally:
        clear_request_tenant()


@override_settings(
    AUTH_JWT_SECRET="p4-rest-secret",
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
    IMPORT_CONTRACT_V2=True,
)
def test_v2_envelope_exposes_p4_fields(env):
    client = _client(env)
    resp = _upload(
        client,
        env["workspace"].id,
        b"uid,title,description\nREQ-P4R-V2,Dry,body\n",
        query="dry_run=true",
    )

    assert resp.status_code in (200, 201), resp.content
    body = resp.json()
    assert body["dry_run"] is True
    assert "conflicts" in body
    assert "reconciled_count" in body
    assert "updated_count" in body
