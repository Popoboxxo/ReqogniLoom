"""Issue #1021 — the REST transport answers 400 for a contradictory hierarchy.

The guard itself lives in ``TraceLinkManager.create`` (see
``traceability/tests/test_hierarchy_contradiction_1021.py``), which is shared by
the REST ViewSet, the MCP tools and the Layer-2 facade. This test pins the
*user-visible* half of task 1: ``POST /api/v1/tracelinks/`` answers **400** with
a message that names the contradiction, instead of the 201 that used to create
the cyclic hierarchy and silently switch TRACE-P1/VERIF-P8 off for it.
"""
from __future__ import annotations

import json

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


def _create_link(client, source_id: str, target_id: str, link_type: str):
    return client.post(
        "/api/v1/tracelinks/",
        {"source_id": source_id, "target_id": target_id, "link_type": link_type},
        format="json",
    )


def test_contradictory_hierarchy_pair_is_rejected_with_a_400(
    authed_client, workspace
) -> None:
    parent = _create_requirement(authed_client, workspace.id, "Parent")
    child = _create_requirement(authed_client, workspace.id, "Child")

    first = _create_link(authed_client, parent["id"], child["id"], "decomposes")
    assert first.status_code == 201, first.content

    # Same pair, same direction, inverse meaning: "a decomposes into b" *and*
    # "a derives from b" cannot both hold.
    conflict = _create_link(authed_client, parent["id"], child["id"], "derives-from")
    assert conflict.status_code == 400, conflict.content
    body = json.dumps(conflict.json())
    assert "Contradictory hierarchy link" in body
    assert "decomposes" in body
    assert "derives-from" in body


def test_the_consistent_direction_of_the_same_pair_is_still_accepted(
    authed_client, workspace
) -> None:
    """``parent --decomposes--> child`` + ``child --derives-from--> parent``.

    The guided "Ableiten" flow writes exactly this pair; it is one fact stated
    twice, not a contradiction, and must keep working over REST.
    """
    parent = _create_requirement(authed_client, workspace.id, "Parent")
    child = _create_requirement(authed_client, workspace.id, "Child")

    assert _create_link(
        authed_client, parent["id"], child["id"], "decomposes"
    ).status_code == 201
    twin = _create_link(authed_client, child["id"], parent["id"], "derives-from")
    assert twin.status_code == 201, twin.content


def test_a_requirement_derived_from_a_stakeholder_need_is_still_accepted(
    authed_client, workspace
) -> None:
    """The L1 anchor is not a hierarchy cycle and must not be caught by the guard."""
    need = authed_client.post(
        "/api/v1/needs/",
        {"workspace_id": str(workspace.id), "title": "Need"},
        format="json",
    )
    assert need.status_code == 201, need.content

    requirement = _create_requirement(authed_client, workspace.id, "L1")
    link = _create_link(
        authed_client, requirement["id"], need.json()["id"], "derives-from"
    )
    assert link.status_code == 201, link.content
