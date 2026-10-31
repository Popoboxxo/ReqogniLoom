"""F1.2-T1 (#1374, finding R-F9-1) — a Diagram publishes its Artifact id.

A Diagram is a valid TraceLink endpoint only through its backing
``persistence.Artifact`` row (``Diagram.artifact``), not through ``Diagram.id``:
``POST /api/v1/trace-links/`` resolves both endpoints to *Artifact* ids. As
long as the REST/MCP responses published only ``id``, a client had no way to
link a diagram at all — it would have to guess that ``Artifact.objects.get(
diagram=…)`` exists.

This module pins the additive contract:

* ``GET /api/v1/diagrams/{id}/`` and ``GET /api/v1/diagrams/`` publish
  ``artifact_id`` (the backing Artifact id) and ``global_uuid`` (the same value
  under the identity name Requirement/Glossary already use, #1261/#1270);
* the published ``artifact_id`` is directly usable as a TraceLink endpoint.

``artifact_id`` is ``null`` for a workspace-less legacy Diagram (no backing
Artifact can exist — ``Artifact.workspace`` is not nullable), so the field is
nullable rather than absent.
"""
from __future__ import annotations

import pytest

from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact

pytestmark = pytest.mark.django_db

_BLOCK_PAYLOAD = '{"nodes": [{"id": "A", "label": "Login"}]}'


def _create_diagram(client, workspace_id, name: str = "Linkable Diagram") -> dict:
    resp = client.post(
        "/api/v1/diagrams/",
        {
            "workspace_id": str(workspace_id),
            "name": name,
            "diagram_type": "block",
            "payload_format": "json",
            "content": _BLOCK_PAYLOAD,
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()


def _create_requirement(client, workspace_id, title: str) -> dict:
    resp = client.post(
        "/api/v1/requirements/",
        {"workspace_id": str(workspace_id), "title": title},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()


def _backing_artifact_id(tenant_id, diagram_id: str) -> str:
    """Ground truth: the Artifact row the Diagram owns."""
    set_request_tenant(tenant_id)
    try:
        return str(Artifact.objects.get(diagram__id=diagram_id).id)
    finally:
        clear_request_tenant()


def test_create_response_exposes_the_backing_artifact_id(
    authed_client, workspace
) -> None:
    """The create response is the client's first (and often only) read."""
    created = _create_diagram(authed_client, workspace.id)

    assert "artifact_id" in created, created
    assert "global_uuid" in created, created
    assert created["artifact_id"] == _backing_artifact_id(
        workspace.tenant_id, created["id"]
    )
    assert created["global_uuid"] == created["artifact_id"]


def test_detail_exposes_the_backing_artifact_id(authed_client, workspace) -> None:
    created = _create_diagram(authed_client, workspace.id)

    resp = authed_client.get(f"/api/v1/diagrams/{created['id']}/")
    assert resp.status_code == 200, resp.content

    body = resp.json()
    assert body["artifact_id"] == _backing_artifact_id(
        workspace.tenant_id, created["id"]
    )
    # Same value under the identity name (#1261/#1270 parity).
    assert body["global_uuid"] == body["artifact_id"]


def test_list_exposes_the_backing_artifact_id(authed_client, workspace) -> None:
    created = _create_diagram(authed_client, workspace.id)

    resp = authed_client.get(f"/api/v1/diagrams/?workspace_id={workspace.id}")
    assert resp.status_code == 200, resp.content

    rows = resp.json()["results"]
    row = next(r for r in rows if r["id"] == created["id"])
    assert row["artifact_id"] == _backing_artifact_id(
        workspace.tenant_id, created["id"]
    )
    assert row["global_uuid"] == row["artifact_id"]


def test_published_artifact_id_is_a_usable_trace_link_target(
    authed_client, workspace
) -> None:
    """The whole point of #1374: the published id actually links."""
    diagram = _create_diagram(authed_client, workspace.id)
    requirement = _create_requirement(authed_client, workspace.id, "Login form")

    resp = authed_client.post(
        "/api/v1/trace-links/",
        {
            "source_id": requirement["id"],
            "target_id": diagram["artifact_id"],
            "link_type": "references",
        },
        format="json",
    )

    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["link_type"] == "references"
    assert body["source_id"] == requirement["artifact_id"]
    assert body["target_id"] == diagram["artifact_id"]
