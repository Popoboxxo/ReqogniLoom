"""Q1.6: rationale survives a real REST round-trip, suspect markers are visible.

The serializer alone proves nothing here: every TraceLink endpoint feeds
``TraceLinkSerializer`` from a plain dict built by ``_tracelink_to_dict`` (or,
for the ``?artifact_id=`` branch, by hand), and the create view builds the
``create_trace_link`` kwargs itself. A field can therefore be declared,
validated and still be invisible on the wire / dropped on write. These tests
pin the wire contract instead of the serializer.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db

_SUSPECT_KEYS = ("rationale", "suspect_flagged_at", "suspect_source_change")


def _create_requirement(client, workspace_id: str, title: str) -> dict:
    resp = client.post(
        "/api/v1/requirements/",
        {"workspace_id": str(workspace_id), "title": title},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()


def _create_link(client, source: dict, target: dict, **extra) -> dict:
    resp = client.post(
        "/api/v1/tracelinks/",
        {
            "source_id": source["id"],
            "target_id": target["id"],
            "link_type": "decomposes",
            **extra,
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()


def test_create_persists_rationale(authed_client, workspace) -> None:
    """A validated rationale must reach the database, not just the 201 body."""
    parent = _create_requirement(authed_client, workspace.id, "L1 requirement")
    child = _create_requirement(authed_client, workspace.id, "L2 requirement")

    created = _create_link(
        authed_client, parent, child, rationale="workshop decision 2026-09"
    )
    assert created["rationale"] == "workshop decision 2026-09"

    # Read back through a *different* endpoint: a create view that echoed the
    # request payload without persisting would pass the assertion above.
    from persistence.models import TraceLink

    assert (
        TraceLink.unscoped.get(pk=created["id"]).rationale
        == "workshop decision 2026-09"
    )

    listed = authed_client.get(
        f"/api/v1/tracelinks/?workspace_id={workspace.id}"
    ).json()["results"]
    assert [link["rationale"] for link in listed] == ["workshop decision 2026-09"]


def test_rationale_defaults_to_empty_string(authed_client, workspace) -> None:
    """Omitting it stays legal — the field is optional (existing clients)."""
    parent = _create_requirement(authed_client, workspace.id, "L1 requirement")
    child = _create_requirement(authed_client, workspace.id, "L2 requirement")

    assert _create_link(authed_client, parent, child)["rationale"] == ""


def test_suspect_markers_are_exposed_and_null(authed_client, workspace) -> None:
    """Visible on every listing shape, and null until propagation writes them."""
    parent = _create_requirement(authed_client, workspace.id, "L1 requirement")
    child = _create_requirement(authed_client, workspace.id, "L2 requirement")
    created = _create_link(authed_client, parent, child, rationale="why not")

    workspace_listed = authed_client.get(
        f"/api/v1/tracelinks/?workspace_id={workspace.id}"
    ).json()["results"][0]
    # The ?artifact_id= branch builds its own dict and is what TraceLinkPanel
    # calls — it must ship the same keys as the workspace listing.
    artifact_listed = authed_client.get(
        f"/api/v1/tracelinks/?workspace_id={workspace.id}"
        f"&artifact_id={parent['artifact_id']}"
    ).json()["results"][0]

    for payload in (created, workspace_listed, artifact_listed):
        assert all(key in payload for key in _SUSPECT_KEYS), payload
        assert payload["suspect_flagged_at"] is None
        assert payload["suspect_source_change"] is None
