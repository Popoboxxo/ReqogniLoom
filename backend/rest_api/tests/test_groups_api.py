"""P6.2: group REST surface."""
from __future__ import annotations

import pytest

from application.artifact_service import append_sort_key
from persistence.models import Artifact, Requirement

pytestmark = pytest.mark.django_db


def _requirement(tenant, workspace, title):
    artifact = Artifact.unscoped.create(
        tenant=tenant,
        workspace=workspace,
        artifact_type="Requirement",
        sort_key=append_sort_key(workspace.id, None, "Requirement"),
    )
    return Requirement.unscoped.create(
        tenant=tenant,
        artifact=artifact,
        workspace=workspace,
        title=title,
        uid=f"R-{title}",
    )


def test_create_group_add_move_and_list_members(authed_client, tenant, workspace):
    first = _requirement(tenant, workspace, "First")
    second = _requirement(tenant, workspace, "Second")

    created = authed_client.post(
        "/api/v1/groups/",
        {"workspace_id": str(workspace.id), "title": "Group A"},
        format="json",
    )
    assert created.status_code == 201, created.content
    group_id = created.json()["id"]

    for requirement in (first, second):
        response = authed_client.post(
            f"/api/v1/groups/{group_id}/members/",
            {"requirement_id": str(requirement.id)},
            format="json",
        )
        assert response.status_code == 200, response.content

    members = authed_client.get(f"/api/v1/groups/{group_id}/members/")
    assert members.status_code == 200
    order = [row["requirement_artifact_id"] for row in members.json()["members"]]
    assert order == [str(first.artifact_id), str(second.artifact_id)]

    moved = authed_client.post(
        f"/api/v1/groups/{group_id}/members/move/",
        {"requirement_id": str(first.id), "after_id": members.json()["members"][1]["trace_link_id"]},
        format="json",
    )
    assert moved.status_code == 200, moved.content

    final = authed_client.get(f"/api/v1/groups/{group_id}/members/").json()["members"]
    assert [row["requirement_artifact_id"] for row in final] == [
        str(second.artifact_id),
        str(first.artifact_id),
    ]

    listed = authed_client.get(f"/api/v1/groups/?workspace_id={workspace.id}")
    assert listed.status_code == 200
    assert listed.json()["results"][0]["title"] == "Group A"
