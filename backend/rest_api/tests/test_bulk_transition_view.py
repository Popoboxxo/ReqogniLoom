"""Slice 2 (Tabellenansicht) — ``POST /api/v1/artifacts/bulk-transition/``.

The service behind it is covered in
``application/tests/test_bulk_update_service_transition.py``; this file pins the
*transport*:

* **route resolution** — the path reaches ``ArtifactBulkTransitionView`` and is
  not swallowed by the router's ``artifacts/<pk>/`` detail pattern;
* **200** roundtrip with **partial** failures in the same body (the specified
  behaviour: the graph refusing one row does not turn the request into an
  error);
* **400** for a request defect (blank reason, 101 ids, ids of two workspaces);
* **403** for a caller without a write role in the workspace the ids belong to —
  including an editor of workspace B acting on A's rows;
* the route declares **no** ``If-Match`` (contract gate
  ``test_conditional_request_contract_1397``) and its operation is part of the
  committed OpenAPI inventory.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from django.urls import resolve
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db

COLLECTION = "/api/v1/requirements/"
TRANSITION_URL = "/api/v1/artifacts/bulk-transition/"
MANIFEST_PATH = (
    Path(__file__).with_name("fixtures") / "openapi_operations_manifest.json"
)
_PASSWORD = "hunter2pass"
IN_REVIEW = "in_review"
APPROVED = "approved"


def _provision(workspace: Workspace) -> None:
    set_request_tenant(workspace.tenant_id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="extended",
            item_type="Requirement",
            tenant_id=workspace.tenant_id,
        )
    finally:
        clear_request_tenant()


@pytest.fixture(autouse=True)
def _requirement_workflow(workspace):
    """Provision the extended requirement graph the transitions need."""
    _provision(workspace)


@pytest.fixture
def sibling_workspace(tenant: Tenant) -> Workspace:
    set_request_tenant(tenant.id)
    try:
        sibling = Workspace.objects.create(
            tenant=tenant, name="Sibling WS", preset={"name": "extended"}
        )
    finally:
        clear_request_tenant()
    _provision(sibling)
    return sibling


def _role_client(tenant: Tenant, workspace: Workspace, role: str, label: str) -> APIClient:
    suffix = uuid.uuid4().hex[:8]
    user = User.objects.create(
        username=f"bulk-transition-{label}-{suffix}",
        email=f"bulk-transition-{label}-{suffix}@t.test",
        tenant=tenant,
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=role
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


@pytest.fixture
def transition_editor_client(tenant: Tenant, workspace: Workspace) -> APIClient:
    """Editor in *workspace* (named distinctly from the shared ``editor_client``,
    which is bound to ``tenant_fixture``/``workspace_fixture``)."""
    return _role_client(tenant, workspace, ROLE_EDITOR, "editor")


@pytest.fixture
def transition_viewer_client(tenant: Tenant, workspace: Workspace) -> APIClient:
    return _role_client(tenant, workspace, ROLE_VIEWER, "viewer")


@pytest.fixture
def workspace_admin_client(tenant: Tenant, workspace: Workspace) -> APIClient:
    """Admin in *workspace* (the conftest ``admin_client`` targets another WS)."""
    return _role_client(tenant, workspace, ROLE_ADMIN, "admin")


def _requirement(client: APIClient, workspace: Workspace, title: str) -> dict:
    response = client.post(
        COLLECTION,
        {
            "workspace_id": str(workspace.id),
            "title": title,
            # The extended preset refuses ``in_review -> approved`` without
            # these three, which would mask the graph case under test.
            "description": "System shall behave",
            "acceptance_criteria": "Given X, when Y, then Z",
            "verification_method": "Inspection",
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.json()


def _state_of(requirement_id: str) -> str:
    from workflow.models import WorkflowItemState

    return WorkflowItemState.unscoped.get(
        item_id=uuid.UUID(requirement_id), item_type="Requirement"
    ).current_state


def _body(requirements: list[dict], **overrides) -> dict:
    body = {
        "item_type": "Requirement",
        "ids": [row["artifact_id"] for row in requirements],
        "to_state": IN_REVIEW,
        "change_reason": "bulk review",
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def test_route_resolves_to_the_bulk_transition_view() -> None:
    match = resolve(TRANSITION_URL)

    assert match.url_name == "api-v1-artifact-bulk-transition"
    assert match.func.view_class.__name__ == "ArtifactBulkTransitionView"
    assert "pk" not in match.kwargs


# ---------------------------------------------------------------------------
# Happy path and partial failures
# ---------------------------------------------------------------------------


def test_bulk_transition_200_with_partial_failures(
    workspace_admin_client, transition_editor_client, workspace
) -> None:
    first = _requirement(transition_editor_client, workspace, "Req A")
    approved = _requirement(transition_editor_client, workspace, "Req B")
    third = _requirement(transition_editor_client, workspace, "Req C")

    # Move one row where the graph has no edge back to ``in_review``:
    # draft -> in_review (editor), then in_review -> approved (admin).
    for target, client in ((IN_REVIEW, transition_editor_client), (APPROVED, workspace_admin_client)):
        step = client.post(
            TRANSITION_URL,
            _body([approved], to_state=target, change_reason=f"to {target}"),
            format="json",
        )
        assert step.status_code == 200, step.content
        assert step.json()["failed"] == []

    response = transition_editor_client.post(
        TRANSITION_URL,
        _body([first, approved, third]),
        format="json",
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["transitioned"] == [
        {"artifact_id": first["artifact_id"], "state": IN_REVIEW},
        {"artifact_id": third["artifact_id"], "state": IN_REVIEW},
    ]
    assert len(body["failed"]) == 1
    assert body["failed"][0]["index"] == 1
    assert body["failed"][0]["artifact_id"] == approved["artifact_id"]
    assert body["failed"][0]["code"] == "VALIDATION_ERROR"
    assert set(body["failed"][0]) == {"index", "artifact_id", "code", "message"}
    assert _state_of(first["id"]) == IN_REVIEW
    assert _state_of(approved["id"]) == APPROVED


def test_bulk_transition_roundtrip_writes_the_state(
    workspace_admin_client, transition_editor_client, workspace
) -> None:
    requirement = _requirement(transition_editor_client, workspace, "Single")

    response = transition_editor_client.post(
        TRANSITION_URL, _body([requirement]), format="json"
    )

    assert response.status_code == 200, response.content
    assert response.json()["transitioned"] == [
        {"artifact_id": requirement["artifact_id"], "state": IN_REVIEW}
    ]
    assert _state_of(requirement["id"]) == IN_REVIEW


# ---------------------------------------------------------------------------
# Request defects (400)
# ---------------------------------------------------------------------------


def test_requires_change_reason_400(transition_editor_client, workspace) -> None:
    requirement = _requirement(transition_editor_client, workspace, "No reason")

    response = transition_editor_client.post(
        TRANSITION_URL, _body([requirement], change_reason=""), format="json"
    )

    assert response.status_code == 400, response.content
    assert _state_of(requirement["id"]) == "draft"


def test_over_100_ids_400(transition_editor_client, workspace) -> None:
    requirement = _requirement(transition_editor_client, workspace, "Too many")

    response = transition_editor_client.post(
        TRANSITION_URL,
        _body([requirement], ids=[requirement["artifact_id"]] * 101),
        format="json",
    )

    assert response.status_code == 400, response.content


def test_two_workspaces_400(
    tenant: Tenant,
    transition_editor_client,
    workspace: Workspace,
    sibling_workspace: Workspace,
) -> None:
    sibling_client = _role_client(tenant, sibling_workspace, ROLE_EDITOR, "sibling")
    here = _requirement(transition_editor_client, workspace, "Here")
    there = _requirement(sibling_client, sibling_workspace, "There")

    response = transition_editor_client.post(
        TRANSITION_URL, _body([here, there]), format="json"
    )

    assert response.status_code == 400, response.content
    assert _state_of(here["id"]) == "draft"
    assert _state_of(there["id"]) == "draft"


def test_unknown_field_in_body_400(transition_editor_client, workspace) -> None:
    requirement = _requirement(transition_editor_client, workspace, "Typo")

    response = transition_editor_client.post(
        TRANSITION_URL, _body([requirement], workspace_id=str(workspace.id)),
        format="json",
    )

    assert response.status_code == 400, response.content


# ---------------------------------------------------------------------------
# Auth (403)
# ---------------------------------------------------------------------------


def test_viewer_403(transition_viewer_client, workspace_admin_client, workspace) -> None:
    requirement = _requirement(workspace_admin_client, workspace, "Viewer target")

    response = transition_viewer_client.post(
        TRANSITION_URL, _body([requirement]), format="json"
    )

    assert response.status_code == 403, response.content
    assert _state_of(requirement["id"]) == "draft"


def test_editor_in_b_cannot_transition_a_ids(
    tenant: Tenant, workspace: Workspace, sibling_workspace: Workspace
) -> None:
    """An editor role in *another* workspace must not authorize these rows."""
    owner = _role_client(tenant, workspace, ROLE_EDITOR, "owner")
    requirement = _requirement(owner, workspace, "Workspace A row")
    outsider = _role_client(tenant, sibling_workspace, ROLE_EDITOR, "outsider")

    response = outsider.post(TRANSITION_URL, _body([requirement]), format="json")

    assert response.status_code == 403, response.content
    assert _state_of(requirement["id"]) == "draft"


# ---------------------------------------------------------------------------
# OpenAPI contract
# ---------------------------------------------------------------------------


def test_declares_no_if_match_and_is_in_the_manifest() -> None:
    schema = SchemaGenerator().get_schema(request=None, public=True)
    operation = schema["paths"][TRANSITION_URL]["post"]

    parameters = operation.get("parameters") or []
    assert all(param.get("name") != "If-Match" for param in parameters)
    assert "requestBody" in operation
    assert "200" in operation["responses"]
    assert "400" in operation["responses"]
    assert "403" in operation["responses"]

    import json

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert [TRANSITION_URL, "post"] in manifest["operations"]

