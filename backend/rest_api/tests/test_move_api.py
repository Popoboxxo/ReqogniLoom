"""P1 Task 1.4: REST surface for ``artifact.move`` and the workspace tree."""
from __future__ import annotations

import pytest
from django.db.models import F
from rest_framework.test import APIClient

from application.artifact_service import append_sort_key
from auth_tenancy.models import ROLE_VIEWER, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Tenant, User, Workspace

pytestmark = pytest.mark.django_db


def _artifact(
    tenant: Tenant, workspace: Workspace, artifact_type: str = "Requirement", parent=None
) -> Artifact:
    parent_id = parent.id if parent is not None else None
    return Artifact.unscoped.create(
        tenant=tenant,
        workspace=workspace,
        artifact_type=artifact_type,
        parent=parent,
        sort_key=append_sort_key(workspace.id, parent_id, artifact_type),
    )


def _children(parent: Artifact) -> list[Artifact]:
    return list(
        Artifact.unscoped.filter(parent_id=parent.id).order_by(
            F("sort_key").asc(nulls_last=True), "created_at", "id"
        )
    )


def test_move_between_siblings(authed_client, tenant, workspace):
    root = _artifact(tenant, workspace)
    a = _artifact(tenant, workspace, parent=root)
    b = _artifact(tenant, workspace, parent=root)
    c = _artifact(tenant, workspace, parent=root)

    response = authed_client.post(
        f"/api/v1/artifacts/{c.id}/move/",
        {"parent_id": str(root.id), "after_id": str(a.id)},
        format="json",
    )

    assert response.status_code == 200, response.content
    assert response.json()["sort_key"]
    assert [row.id for row in _children(root)] == [a.id, c.id, b.id]


def test_move_omitted_after_appends_and_null_inserts_first(authed_client, tenant, workspace):
    root = _artifact(tenant, workspace)
    a = _artifact(tenant, workspace, parent=root)
    b = _artifact(tenant, workspace, parent=root)
    _artifact(tenant, workspace, parent=root)

    response = authed_client.post(
        f"/api/v1/artifacts/{a.id}/move/",
        {"parent_id": str(root.id)},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert _children(root)[-1].id == a.id

    response = authed_client.post(
        f"/api/v1/artifacts/{b.id}/move/",
        {"parent_id": str(root.id), "after_id": None},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert _children(root)[0].id == b.id


def test_move_rejects_after_id_from_another_parent(authed_client, tenant, workspace):
    root = _artifact(tenant, workspace)
    other_root = _artifact(tenant, workspace)
    _artifact(tenant, workspace, parent=root)
    stranger = _artifact(tenant, workspace, parent=other_root)

    response = authed_client.post(
        f"/api/v1/artifacts/{root.id}/move/",
        {"parent_id": str(root.id), "after_id": str(stranger.id)},
        format="json",
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_move_rejects_cross_workspace_parent(authed_client, tenant, workspace):
    root = _artifact(tenant, workspace)
    set_request_tenant(tenant.id)
    try:
        other_workspace = Workspace.objects.create(tenant=tenant, name="other")
    finally:
        clear_request_tenant()
    foreign = _artifact(tenant, other_workspace)

    response = authed_client.post(
        f"/api/v1/artifacts/{root.id}/move/",
        {"parent_id": str(foreign.id)},
        format="json",
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_move_requires_write_role(authed_client, tenant, workspace):
    root = _artifact(tenant, workspace)
    child = _artifact(tenant, workspace, parent=root)

    suffix = "viewer-move"
    user = User.objects.create(
        username=suffix, email=f"{suffix}@t.test", tenant=tenant
    )
    user.set_password("hunter2pass")
    user.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_VIEWER
        )
    finally:
        clear_request_tenant()

    viewer = APIClient()
    login = viewer.post(
        "/api/v1/auth/login/",
        {"username": suffix, "password": "hunter2pass"},
        format="json",
    )
    assert login.status_code == 200, login.content
    viewer.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")

    response = viewer.post(
        f"/api/v1/artifacts/{child.id}/move/",
        {"parent_id": None},
        format="json",
    )
    assert response.status_code in (403, 400)
    if response.status_code == 403:
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"


def test_workspace_tree_is_sorted_and_hides_outdated(authed_client, tenant, workspace):
    root = _artifact(tenant, workspace)
    a = _artifact(tenant, workspace, parent=root)
    b = _artifact(tenant, workspace, parent=root)
    hidden = _artifact(tenant, workspace, parent=root)
    Artifact.unscoped.filter(id=hidden.id).update(lifecycle_status="outdated")

    response = authed_client.get(
        f"/api/v1/workspaces/{workspace.id}/tree/?type=requirement"
    )
    assert response.status_code == 200, response.content
    tree = response.json()["tree"]
    assert len(tree) == 1
    assert tree[0]["id"] == str(root.id)
    child_ids = [node["id"] for node in tree[0]["children"]]
    assert child_ids == [str(a.id), str(b.id)]
    assert all(node["sort_key"] for node in tree[0]["children"])


def test_workspace_tree_rejects_unknown_type(authed_client, workspace):
    response = authed_client.get(
        f"/api/v1/workspaces/{workspace.id}/tree/?type=milestone"
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
