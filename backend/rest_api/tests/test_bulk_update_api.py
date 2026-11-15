"""REST surface of the bulk update — ``PATCH /api/v1/artifacts/bulk-update/``.

Slice R3.2 of ``docs/superpowers/plans/2026-11-15-document-view-on-document.md``.
The service behind it (``application.bulk_update_service``) is covered in
``application/tests/test_bulk_update_service.py``; this file pins the *transport*:

* **route resolution** — the path reaches ``ArtifactBulkUpdateView`` and is not
  swallowed by the router's ``artifacts/<pk>/`` detail pattern (the reason the
  route is registered before ``router.urls``);
* **200** roundtrip: the body shape is ``{"updated": [{artifact_id, version}],
  "errors": []}`` and the writes are visible afterwards;
* **400** for a request defect (101 entries, empty list, unknown key);
* **409** for a business refusal with **nothing written** — asserted against the
  stored row, not against the response body;
* **403** for a caller without a write role;
* the route is part of the committed OpenAPI operation manifest *and* the
  generated schema documents request body + 200/400/403/409.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from django.urls import resolve
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_VIEWER, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db

COLLECTION = "/api/v1/documents/"
BULK_URL = "/api/v1/artifacts/bulk-update/"
MANIFEST_PATH = (
    Path(__file__).with_name("fixtures") / "openapi_operations_manifest.json"
)
_PASSWORD = "hunter2pass"


@pytest.fixture(autouse=True)
def _document_workflow(tenant, workspace):
    """Provision the ``document_default`` workflow the create path needs."""
    set_request_tenant(tenant.id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="document_default",
            item_type="Document",
            tenant_id=tenant.id,
        )
    finally:
        clear_request_tenant()


def _document(client: APIClient, workspace, title: str) -> dict:
    response = client.post(
        COLLECTION,
        {
            "workspace_id": str(workspace.id),
            "title": title,
            "kind": "Spec",
            "description": "Bulk update target",
            "body": "# Spec\n\nContent.",
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.json()


def _entry(document: dict, **fields) -> dict:
    return {
        "artifact_id": document["artifact_id"],
        "expected_version": document["version"],
        "fields": fields,
    }


@pytest.fixture
def viewer_client(tenant: Tenant, workspace) -> APIClient:
    """A logged-in user holding only the Viewer role in *workspace*."""
    suffix = uuid.uuid4().hex[:8]
    user = User.objects.create(
        username=f"bulk-viewer-{suffix}",
        email=f"bulk-viewer-{suffix}@t.test",
        tenant=tenant,
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_VIEWER
        )
    finally:
        clear_request_tenant()

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": _PASSWORD},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def test_route_resolves_to_the_bulk_view_and_not_to_the_detail_pattern() -> None:
    match = resolve(BULK_URL)

    assert match.url_name == "api-v1-artifact-bulk-update"
    assert match.func.view_class.__name__ == "ArtifactBulkUpdateView"
    # The router's ``artifacts/<pk>/`` pattern would capture "bulk-update" as a
    # pk if the explicit route were registered after it.
    assert "pk" not in match.kwargs


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_bulk_update_endpoint_roundtrip(authed_client, workspace) -> None:
    first = _document(authed_client, workspace, "Spec A")
    second = _document(authed_client, workspace, "Spec B")
    third = _document(authed_client, workspace, "Spec C")

    response = authed_client.patch(
        BULK_URL,
        {
            "workspace_id": str(workspace.id),
            "entries": [
                _entry(first, title="Spec A (revised)"),
                _entry(second, body="# Spec B\n\nNew body."),
                _entry(third, description="New purpose"),
            ],
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["errors"] == []
    assert [row["artifact_id"] for row in body["updated"]] == [
        first["artifact_id"],
        second["artifact_id"],
        third["artifact_id"],
    ]
    assert [row["version"] for row in body["updated"]] == [2, 2, 2]

    reloaded = authed_client.get(f"{COLLECTION}{first['id']}/")
    assert reloaded.json()["title"] == "Spec A (revised)"
    assert reloaded.json()["version"] == 2

    reloaded = authed_client.get(f"{COLLECTION}{second['id']}/")
    assert reloaded.json()["body"] == "# Spec B\n\nNew body."

    reloaded = authed_client.get(f"{COLLECTION}{third['id']}/")
    assert reloaded.json()["description"] == "New purpose"


# ---------------------------------------------------------------------------
# 400 — request defects
# ---------------------------------------------------------------------------


def test_101_entries_is_400(authed_client, workspace) -> None:
    document = _document(authed_client, workspace, "Spec")
    entries = [_entry(document, title=f"T{i}") for i in range(101)]

    response = authed_client.patch(
        BULK_URL,
        {"workspace_id": str(workspace.id), "entries": entries},
        format="json",
    )

    assert response.status_code == 400, response.content
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    # Nothing was written.
    assert authed_client.get(f"{COLLECTION}{document['id']}/").json()["title"] == "Spec"


def test_empty_entries_is_400(authed_client, workspace) -> None:
    response = authed_client.patch(
        BULK_URL,
        {"workspace_id": str(workspace.id), "entries": []},
        format="json",
    )

    assert response.status_code == 400, response.content
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unknown_key_in_an_entry_is_400(authed_client, workspace) -> None:
    document = _document(authed_client, workspace, "Spec")

    response = authed_client.patch(
        BULK_URL,
        {
            "workspace_id": str(workspace.id),
            "entries": [
                {
                    "artifact_id": document["artifact_id"],
                    "expected_version": 1,
                    "fields": {"title": "x"},
                    "expected_versions": 1,
                }
            ],
        },
        format="json",
    )

    assert response.status_code == 400, response.content
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# 409 — business refusal, nothing written
# ---------------------------------------------------------------------------


def test_conflict_is_409_and_writes_nothing(authed_client, workspace) -> None:
    updated = _document(authed_client, workspace, "Should stay")
    stale = _document(authed_client, workspace, "Stale")

    response = authed_client.patch(
        BULK_URL,
        {
            "workspace_id": str(workspace.id),
            "entries": [
                _entry(updated, title="Must be rolled back"),
                {
                    "artifact_id": stale["artifact_id"],
                    "expected_version": 99,
                    "fields": {"title": "stale write"},
                },
            ],
        },
        format="json",
    )

    assert response.status_code == 409, response.content
    body = response.json()
    # 409 carries the same envelope as 200 — a client marks the row by index.
    assert body["updated"] == []
    assert [error["index"] for error in body["errors"]] == [1]
    assert body["errors"][0]["code"] == "CONFLICT"
    assert body["errors"][0]["artifact_id"] == stale["artifact_id"]

    # DB assertion through the API: the valid entry was rolled back too.
    reloaded = authed_client.get(f"{COLLECTION}{updated['id']}/").json()
    assert reloaded["title"] == "Should stay"
    assert reloaded["version"] == 1


# ---------------------------------------------------------------------------
# 403 — no write role
# ---------------------------------------------------------------------------


def test_viewer_without_write_role_is_403(viewer_client, authed_client, workspace) -> None:
    document = _document(authed_client, workspace, "Viewer cannot write")

    response = viewer_client.patch(
        BULK_URL,
        {
            "workspace_id": str(workspace.id),
            "entries": [_entry(document, title="nope")],
        },
        format="json",
    )

    assert response.status_code == 403, response.content
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"
    # … and nothing was written.
    reloaded = authed_client.get(f"{COLLECTION}{document['id']}/").json()
    assert reloaded["title"] == "Viewer cannot write"
    assert reloaded["version"] == 1


# ---------------------------------------------------------------------------
# OpenAPI
# ---------------------------------------------------------------------------


def test_openapi_manifest_contains_the_bulk_update_route() -> None:
    document = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    operations = {(path, method) for path, method in document["operations"]}

    assert (BULK_URL, "patch") in operations


@pytest.fixture(scope="module")
def generated_schema() -> dict:
    return SchemaGenerator().get_schema(request=None, public=True)


def test_openapi_documents_bulk_update_route(generated_schema) -> None:
    path = generated_schema["paths"][BULK_URL]
    operation = path["patch"]

    assert operation["summary"]
    # Same body shape as the service contract, not an untyped fallback.
    # drf-spectacular names the component after the serializer and adds its own
    # ``Patched``/``Request`` affixes for a PATCH body; only the stem is ours.
    request_schema = operation["requestBody"]["content"]["application/json"]["schema"]
    assert request_schema["$ref"].endswith("/PatchedBulkUpdateRequestRequest")

    statuses = set(operation["responses"])
    assert {"200", "400", "403", "409"} <= statuses
    assert operation["responses"]["200"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/BulkUpdateResponse")
    assert operation["responses"]["409"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/BulkUpdateResponse")
    assert "x-reqlo-untyped" not in operation
