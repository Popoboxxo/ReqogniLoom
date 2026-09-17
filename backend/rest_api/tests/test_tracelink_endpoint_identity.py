"""TraceLink endpoint identity contract (issues #413, #415, #416).

TraceLink endpoints are **Artifact** ids. Clients, however, address
requirements by their **Requirement** id — the two id spaces are disjoint, and
`create_trace_link` silently resolves the latter into the former
(`TraceLinkService._resolve_artifact_id`). A client that is not told the
backing `artifact_id` therefore cannot decide whether an endpoint of a link
*is* the requirement it currently displays. Three UI defects came out of
exactly that gap: the traceability list fell back to truncated UUIDs (#413),
the impact tree's root node had no title (#415), and the requirement editor's
hierarchy panel resolved every link back to the requirement itself (#416).

These tests pin the contract the frontend now relies on:
  * requirement responses expose a non-null ``artifact_id``;
  * a link created from Requirement ids comes back keyed by Artifact ids;
  * the workspace-level list ships resolved titles and types for both ends.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


def _create_requirement(client, workspace_id: str, title: str) -> dict:
    resp = client.post(
        "/api/v1/requirements/",
        {"workspace_id": str(workspace_id), "title": title},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()


def test_requirement_response_exposes_artifact_id(authed_client, workspace) -> None:
    """#413/#416: without this field the UI cannot join links to entities."""
    created = _create_requirement(authed_client, workspace.id, "L1 requirement")
    assert created.get("artifact_id"), created

    listed = authed_client.get(
        f"/api/v1/requirements/?workspace_id={workspace.id}"
    ).json()["results"]
    assert all(r.get("artifact_id") for r in listed), listed

    detail = authed_client.get(f"/api/v1/requirements/{created['id']}/").json()
    assert detail["artifact_id"] == created["artifact_id"]
    # The two id spaces really are disjoint — a test that assumed otherwise
    # would pass while the UI kept rendering the artifact itself.
    assert detail["artifact_id"] != detail["id"]


def test_tracelink_endpoints_use_artifact_ids(authed_client, workspace) -> None:
    """A link created from Requirement ids is stored/returned by Artifact id."""
    parent = _create_requirement(authed_client, workspace.id, "L1 requirement")
    child = _create_requirement(authed_client, workspace.id, "L2 requirement")

    created = authed_client.post(
        "/api/v1/tracelinks/",
        {
            "source_id": parent["id"],
            "target_id": child["id"],
            "link_type": "decomposes",
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    link = created.json()
    assert link["source_id"] == parent["artifact_id"]
    assert link["target_id"] == child["artifact_id"]
    assert link["source_id"] != parent["id"]


def test_workspace_link_list_ships_titles_and_types(authed_client, workspace) -> None:
    """#413: the readable metadata the traceability list must render."""
    parent = _create_requirement(authed_client, workspace.id, "L1 requirement")
    child = _create_requirement(authed_client, workspace.id, "L2 requirement")
    authed_client.post(
        "/api/v1/tracelinks/",
        {
            "source_id": parent["id"],
            "target_id": child["id"],
            "link_type": "decomposes",
        },
        format="json",
    )

    listed = authed_client.get(
        f"/api/v1/tracelinks/?workspace_id={workspace.id}"
    ).json()["results"]
    assert len(listed) == 1, listed
    link = listed[0]
    assert link["source_title"] == "L1 requirement"
    assert link["target_title"] == "L2 requirement"
    assert link["source_type"] == "Requirement"
    assert link["target_type"] == "Requirement"
    # And the endpoints stay in the Artifact id space.
    assert {link["source_id"], link["target_id"]} == {
        parent["artifact_id"],
        child["artifact_id"],
    }
