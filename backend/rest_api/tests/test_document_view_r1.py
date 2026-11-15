"""REST surface of the document reading view — ``GET /documents/{id}/view/``.

Slice R1 of ``docs/superpowers/plans/2026-11-15-document-view-on-document.md``.
The route is an ``@action`` on ``DocumentViewSet`` (no ``urls.py`` entry, no new
write path), so this suite pins:

* ``200`` with the documented field form and ``ETag: "<version>"``,
* ``403`` for an item-level denial (the RBAC matrix alone is not the answer),
* ``404`` for an unknown or foreign-tenant id (no existence oracle) and
  ``400`` for a malformed path segment (#271),
* the route is *inventoried*: it resolves to the ``view`` action and is part of
  the committed OpenAPI operation manifest
  (``rest_api/tests/fixtures/openapi_operations_manifest.json``).

The full schema-completeness gate runs separately
(``test_schema_completeness_1388.py``); this file deliberately does not
regenerate the whole OpenAPI document.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from django.urls import resolve
from rest_framework.test import APIClient

from auth_tenancy.models import ItemPermission
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Document, User
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db

COLLECTION = "/api/v1/documents/"
MANIFEST_PATH = (
    Path(__file__).with_name("fixtures") / "openapi_operations_manifest.json"
)

BODY = "# System Spec\n\nPurpose.\n\n## Scope\n\nEverything.\n"


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


@pytest.fixture
def document(authed_client: APIClient, workspace) -> dict:
    response = authed_client.post(
        COLLECTION,
        {
            "workspace_id": str(workspace.id),
            "title": "System Spec",
            "kind": "Spec",
            "description": "How the system behaves",
            "body": BODY,
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.json()


def _view_url(document_id) -> str:
    return f"{COLLECTION}{document_id}/view/"


def test_view_returns_reading_object(authed_client, document) -> None:
    response = authed_client.get(_view_url(document["id"]))

    assert response.status_code == 200, response.content
    payload = response.json()
    assert set(payload) == {
        "id",
        "artifact_id",
        "uid",
        "title",
        "kind",
        "description",
        "body",
        "doc_date",
        "version",
        "status",
        "frozen_at",
        "frozen_fields",
        "editable_fields",
        "chapters",
        "projection",
    }
    assert payload["id"] == document["id"]
    assert payload["title"] == "System Spec"
    assert payload["status"] == "Entwurf"
    assert payload["version"] == 1
    assert payload["frozen_fields"] == []
    assert payload["editable_fields"] == ["title", "description", "body", "doc_date"]
    assert payload["chapters"] == [
        {
            "number": "1",
            "level": 1,
            "title": "System Spec",
            "anchor": "system-spec",
            "body": "Purpose.",
        },
        {
            "number": "1.1",
            "level": 2,
            "title": "Scope",
            "anchor": "scope",
            "body": "Everything.",
        },
    ]
    assert payload["projection"] == {
        "projection_mode": "none",
        "source_path": "",
        "projected_sha256": "",
    }


def test_view_emits_etag(authed_client, document) -> None:
    response = authed_client.get(_view_url(document["id"]))

    assert response["ETag"] == f'"{document["version"]}"'


def test_view_is_read_only(authed_client, document, workspace) -> None:
    """The reading route must not touch the entity version."""
    authed_client.get(_view_url(document["id"]))
    authed_client.get(_view_url(document["id"]))

    response = authed_client.get(f"{COLLECTION}{document['id']}/")
    assert response.status_code == 200
    assert response.json()["version"] == document["version"]


def test_item_level_deny_is_403(authed_client, tenant, workspace, document) -> None:
    user = User.objects.get(username="bundleadmin")
    set_request_tenant(tenant.id)
    try:
        ItemPermission.objects.create(
            tenant=tenant,
            user=user,
            workspace=workspace,
            artifact_id=document["artifact_id"],
            permission_level="none",
        )
    finally:
        clear_request_tenant()

    response = authed_client.get(_view_url(document["id"]))

    assert response.status_code == 403, response.content
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"


def test_unknown_id_is_404(authed_client) -> None:
    response = authed_client.get(_view_url(uuid.uuid4()))

    assert response.status_code == 404, response.content
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_malformed_id_is_400(authed_client) -> None:
    """#271: a garbage pk is a request defect (400), not a missing resource.

    The distinction is deliberate — "you sent garbage" must not be
    indistinguishable from "well-formed id, no such row".
    """
    response = authed_client.get(f"{COLLECTION}not-a-uuid/view/")

    assert response.status_code == 400, response.content
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_foreign_tenant_document_is_404(authed_client, workspace, document) -> None:
    """Another tenant's document is indistinguishable from a missing one."""
    from persistence.models import Tenant, Workspace

    other = Tenant.objects.create(
        name="Reading REST Other",
        slug=f"reading-rest-other-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    set_request_tenant(other.id)
    try:
        other_workspace = Workspace.objects.create(
            tenant=other, name="reading-rest-other-ws", preset={"name": "standard"}
        )
        create_default_workflow(
            workspace_id=other_workspace.id,
            preset="document_default",
            item_type="Document",
            tenant_id=other.id,
        )
        from application.document_service import DocumentService
        from auth_tenancy.context import AuthContext

        ctx = AuthContext(
            user_id=uuid.uuid4(),
            tenant_id=other.id,
            active_roles=("admin",),
            auth_method="test",
            tenant_name=other.name,
        )
        foreign = DocumentService().create_document(
            other_workspace.id,
            ctx,
            title="Foreign",
            kind=Document.Kind.SPEC,
        )
    finally:
        clear_request_tenant()

    response = authed_client.get(_view_url(foreign.id))

    assert response.status_code == 404, response.content


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


def test_view_route_resolves_to_the_viewset_action() -> None:
    match = resolve("/api/v1/documents/00000000-0000-0000-0000-000000000000/view/")

    assert match.func.cls.__name__ == "DocumentViewSet"
    assert match.func.actions["get"] == "view"


def test_openapi_manifest_contains_the_view_route() -> None:
    document = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    operations = {(path, method) for path, method in document["operations"]}

    assert ("/api/v1/documents/{id}/view/", "get") in operations
