"""P4.4: batch lock endpoint for the classic Requirement/Architecture trees.

``GET /api/v1/workspaces/{id}/locks/?type=requirement|architecture`` returns
only the artifacts whose current workflow state carries
``state_meta.freeze_on_enter``. The read is batched: the freeze-triggering
states are read once per item type and ``current_states`` resolves every item
in one query, so the cost is constant in the number of items.
"""
from __future__ import annotations

import uuid

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    ArchitectureElement,
    Artifact,
    Requirement,
    Tenant,
    User,
    Workspace,
)
from workflow.models import WorkflowEngineDefinition, WorkflowItemState

pytestmark = pytest.mark.django_db

FROZEN = "frozen"
DRAFT = "draft"


def _definition(tenant, workspace, item_type: str) -> WorkflowEngineDefinition:
    return WorkflowEngineDefinition.unscoped.create(
        tenant=tenant,
        workspace_id=workspace.id,
        item_type=item_type,
        preset="standard",
        workflow_json={
            "states": [DRAFT, FROZEN],
            "transitions": [],
            "state_meta": {FROZEN: {"freeze_on_enter": True}},
        },
    )


def _state(tenant, workspace, definition, item, item_type: str, state: str):
    return WorkflowItemState.unscoped.create(
        tenant=tenant,
        item_id=item.id,
        item_type=item_type,
        workspace_id=workspace.id,
        definition=definition,
        current_state=state,
    )


def _requirement(tenant, workspace, *, title: str, uid: str) -> Requirement:
    artifact = Artifact.unscoped.create(
        tenant=tenant,
        workspace=workspace,
        artifact_type="Requirement",
        sort_key="a0",
    )
    return Requirement.unscoped.create(
        tenant=tenant,
        artifact=artifact,
        workspace=workspace,
        title=title,
        uid=uid,
    )


def _element(tenant, workspace, *, title: str, uid: str) -> ArchitectureElement:
    artifact = Artifact.unscoped.create(
        tenant=tenant,
        workspace=workspace,
        artifact_type="ArchitectureElement",
        sort_key="a0",
    )
    return ArchitectureElement.unscoped.create(
        tenant=tenant,
        artifact=artifact,
        workspace=workspace,
        title=title,
        uid=uid,
    )


def _bulk_requirements(tenant, workspace, count: int) -> None:
    artifacts = [
        Artifact(
            tenant=tenant,
            workspace=workspace,
            artifact_type="Requirement",
            sort_key=f"a{index:05d}",
        )
        for index in range(count)
    ]
    Artifact.unscoped.bulk_create(artifacts)
    Requirement.unscoped.bulk_create(
        [
            Requirement(
                tenant=tenant,
                artifact=artifact,
                workspace=workspace,
                title=f"Bulk {index}",
            )
            for index, artifact in enumerate(artifacts)
        ]
    )


def _locks_url(workspace, item_type: str) -> str:
    return f"/api/v1/workspaces/{workspace.id}/locks/?type={item_type}"


def test_locks_returns_only_frozen_requirements(tenant, workspace, authed_client):
    definition = _definition(tenant, workspace, "Requirement")
    frozen = _requirement(tenant, workspace, title="Frozen", uid="R-F")
    open_req = _requirement(tenant, workspace, title="Open", uid="R-O")
    _state(tenant, workspace, definition, frozen, "Requirement", FROZEN)
    _state(tenant, workspace, definition, open_req, "Requirement", DRAFT)

    response = authed_client.get(_locks_url(workspace, "requirement"))

    assert response.status_code == 200, response.content
    assert response.json() == {"locks": {str(frozen.id): FROZEN}}


def test_locks_returns_only_frozen_architecture_elements(
    tenant, workspace, authed_client
):
    definition = _definition(tenant, workspace, "ArchitectureElement")
    frozen = _element(tenant, workspace, title="Frozen", uid="E-F")
    open_el = _element(tenant, workspace, title="Open", uid="E-O")
    _state(tenant, workspace, definition, frozen, "ArchitectureElement", FROZEN)
    _state(tenant, workspace, definition, open_el, "ArchitectureElement", DRAFT)

    response = authed_client.get(_locks_url(workspace, "architecture"))

    assert response.status_code == 200, response.content
    assert response.json() == {"locks": {str(frozen.id): FROZEN}}


def test_locks_is_empty_when_nothing_is_frozen(tenant, workspace, authed_client):
    definition = _definition(tenant, workspace, "Requirement")
    open_req = _requirement(tenant, workspace, title="Open", uid="R-O")
    _state(tenant, workspace, definition, open_req, "Requirement", DRAFT)

    response = authed_client.get(_locks_url(workspace, "requirement"))

    assert response.status_code == 200, response.content
    assert response.json() == {"locks": {}}


def test_locks_rejects_a_missing_or_unknown_type(tenant, workspace, authed_client):
    base = f"/api/v1/workspaces/{workspace.id}/locks/"
    for url in (base, f"{base}?type=document", f"{base}?type="):
        response = authed_client.get(url)
        assert response.status_code == 400, (url, response.content)
        message = response.json()["error"]["message"]
        assert "type" in message


def test_locks_is_tenant_isolated(tenant, workspace, authed_client):
    other_tenant = Tenant.objects.create(
        name="Other", slug=f"other-{uuid.uuid4().hex[:8]}"
    )
    set_request_tenant(other_tenant.id)
    try:
        other_workspace = Workspace.objects.create(
            tenant=other_tenant, name="Other WS", preset={"name": "standard"}
        )
    finally:
        clear_request_tenant()

    definition = _definition(other_tenant, other_workspace, "Requirement")
    foreign = _requirement(
        other_tenant, other_workspace, title="Foreign frozen", uid="R-X"
    )
    _state(other_tenant, other_workspace, definition, foreign, "Requirement", FROZEN)

    # The foreign workspace itself is a 404 for this tenant's caller.
    foreign_response = authed_client.get(_locks_url(other_workspace, "requirement"))
    assert foreign_response.status_code == 404, foreign_response.content

    # And the caller's own workspace response never leaks the foreign row.
    own_response = authed_client.get(_locks_url(workspace, "requirement"))
    assert own_response.status_code == 200, own_response.content
    assert str(foreign.id) not in own_response.json()["locks"]


def test_locks_requires_read_access(tenant, workspace):
    user = User.objects.create(
        username=f"norole-{uuid.uuid4().hex[:8]}",
        email=f"norole-{uuid.uuid4().hex[:8]}@t.test",
        tenant=tenant,
    )
    user.set_password("hunter2pass")
    user.save(update_fields=["password"])

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": "hunter2pass"},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")

    response = client.get(_locks_url(workspace, "requirement"))

    assert response.status_code == 403, response.content
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"


def test_locks_query_count_is_independent_of_item_count(
    tenant, workspace, authed_client
):
    _definition(tenant, workspace, "Requirement")
    _bulk_requirements(tenant, workspace, 10)
    url = _locks_url(workspace, "requirement")

    # Warm-up: permission/preset caches.
    assert authed_client.get(url).status_code == 200
    with CaptureQueriesContext(connection) as small:
        assert authed_client.get(url).status_code == 200

    _bulk_requirements(tenant, workspace, 190)

    with CaptureQueriesContext(connection) as large:
        response = authed_client.get(url)
    assert response.status_code == 200
    assert response.json() == {"locks": {}}

    assert len(large.captured_queries) == len(small.captured_queries), (
        "locks must stay one batched read: "
        f"10 items -> {len(small.captured_queries)} queries, "
        f"200 items -> {len(large.captured_queries)} queries"
    )
