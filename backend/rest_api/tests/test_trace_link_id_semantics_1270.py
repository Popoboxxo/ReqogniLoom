"""Artifact identity is unambiguous: `id` vs `artifact_id`, and links publish both (#1270).

An artifact read exposes two identifiers — the entity primary key (`id`) and the
canonical *Artifact* id (`artifact_id`) — while every TraceLink stores and
returns the Artifact id in `source_id`/`target_id`. Joining a Requirement's `id`
against a link's `source_id` therefore silently produces plausible-but-wrong
coverage (the QA run read "100% orphans" instead of ~0.7%).

The fix is additive: `source_id`/`target_id` keep their values, and the link
read now also exposes the unambiguous aliases `source_artifact_id` /
`target_artifact_id`. These tests pin the semantics end to end through HTTP:

* a Requirement read carries both ids and they differ;
* a link read publishes the aliases with the same values as source_id/target_id;
* the link endpoint joins against the artifact's `artifact_id`, not its `id`.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


def _create_requirement(client, workspace_id, title: str) -> dict:
    resp = client.post(
        "/api/v1/requirements/",
        {"workspace_id": str(workspace_id), "title": title},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()


def test_requirement_read_exposes_both_ids_and_they_differ(authed_client, workspace) -> None:
    """`id` (entity PK) and `artifact_id` (canonical) are both present, distinct."""
    req = _create_requirement(authed_client, workspace.id, "REQ for #1270")

    assert req["id"]
    assert req["artifact_id"]
    assert req["id"] != req["artifact_id"], (
        "the two id spaces must be distinct, otherwise this guard is meaningless"
    )
    # #1261: the stable global UUID is exposed read-only and equals artifact_id.
    assert req["global_uuid"] == req["artifact_id"]


def test_trace_link_read_publishes_artifact_id_aliases(authed_client, workspace) -> None:
    """The link read carries source/target_artifact_id equal to source/target_id."""
    source = _create_requirement(authed_client, workspace.id, "Source req")
    target = _create_requirement(authed_client, workspace.id, "Target req")

    created = authed_client.post(
        "/api/v1/tracelinks/",
        {
            "source_id": source["id"],
            "target_id": target["id"],
            "link_type": "decomposes",
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    link = created.json()

    # Backward-compatible keys keep their values (stored Artifact ids).
    assert link["source_id"] == source["artifact_id"]
    assert link["target_id"] == target["artifact_id"]
    # Unambiguous aliases are present and identical (#1270).
    assert link["source_artifact_id"] == link["source_id"]
    assert link["target_artifact_id"] == link["target_id"]

    # The list path is a separate hand-built dict — pin it too.
    listed = authed_client.get(
        f"/api/v1/tracelinks/?workspace_id={workspace.id}"
    ).json()["results"]
    assert len(listed) == 1, listed
    assert listed[0]["source_artifact_id"] == source["artifact_id"]
    assert listed[0]["target_artifact_id"] == target["artifact_id"]


def test_link_endpoints_join_against_artifact_id_not_id(authed_client, workspace) -> None:
    """The documented join (`artifact_id`) resolves; the mistaken one (`id`) does not."""
    source = _create_requirement(authed_client, workspace.id, "Joinable req")
    target = _create_requirement(authed_client, workspace.id, "Other req")

    created = authed_client.post(
        "/api/v1/tracelinks/",
        {
            "source_id": source["id"],
            "target_id": target["id"],
            "link_type": "decomposes",
        },
        format="json",
    )
    assert created.status_code == 201, created.content

    links = authed_client.get(
        f"/api/v1/tracelinks/?workspace_id={workspace.id}"
    ).json()["results"]

    # Correct join: the link's source matches the requirement's artifact_id.
    assert any(link["source_artifact_id"] == source["artifact_id"] for link in links)
    # Wrong join (the hazard): no link's source equals the entity `id`.
    assert all(link["source_id"] != source["id"] for link in links)
