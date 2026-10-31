"""F1.2-T2 (#1374, PR-F3b) — creating a Diagram requires a workspace.

A Diagram is a TraceLink endpoint only through its backing ``Artifact``, and
``Artifact.workspace`` is not nullable. A Diagram created without a workspace
can therefore never be linked, never enter a workspace-scoped baseline and
never show up in a workspace-scoped list — it is an orphan row. F1.2-T2 makes
``workspace_id`` a required field of ``POST /api/v1/diagrams/``:

* missing ``workspace_id``   -> 400 ``VALIDATION_ERROR`` "workspace_id is required"
* malformed ``workspace_id`` -> 400 ``VALIDATION_ERROR``
  "workspace_id must be a valid UUID"
* valid ``workspace_id``     -> 201 with a non-null ``artifact_id``

Deliberate breaking change (PR-F3b): the pre-F1.2-T2 endpoint answered 201 with
``artifact_id: null`` for a workspace-less body.
"""
from __future__ import annotations

import pytest

from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact

pytestmark = pytest.mark.django_db

_BLOCK_PAYLOAD = '{"nodes": [{"id": "A", "label": "Login"}]}'


def _body(**overrides: object) -> dict:
    body = {
        "name": "Diagram Without Workspace",
        "diagram_type": "block",
        "payload_format": "json",
        "content": _BLOCK_PAYLOAD,
    }
    body.update(overrides)
    return body


def _backing_artifact_id(tenant_id, diagram_id: str) -> str:
    """Ground truth: the Artifact row the Diagram owns."""
    set_request_tenant(tenant_id)
    try:
        return str(Artifact.objects.get(diagram__id=diagram_id).id)
    finally:
        clear_request_tenant()


def test_create_without_workspace_is_400(authed_client) -> None:
    """No workspace_id -> 400, never a 201 with an unlinkable Diagram."""
    resp = authed_client.post("/api/v1/diagrams/", _body(), format="json")

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert resp.json()["error"]["message"] == "workspace_id is required"


def test_create_with_malformed_workspace_is_400(authed_client) -> None:
    """A typo'd UUID is named as such, not reported as absent (#460)."""
    resp = authed_client.post(
        "/api/v1/diagrams/", _body(workspace_id="not-a-uuid"), format="json"
    )

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert resp.json()["error"]["message"] == "workspace_id must be a valid UUID"


def test_create_with_workspace_has_artifact(authed_client, workspace) -> None:
    """With a workspace the Diagram is linkable from birth (backing Artifact)."""
    resp = authed_client.post(
        "/api/v1/diagrams/",
        _body(workspace_id=str(workspace.id)),
        format="json",
    )

    assert resp.status_code == 201, resp.content
    created = resp.json()
    assert created["workspace_id"] == str(workspace.id)
    assert created["artifact_id"] is not None
    assert created["artifact_id"] == _backing_artifact_id(
        workspace.tenant_id, created["id"]
    )
    assert created["global_uuid"] == created["artifact_id"]
