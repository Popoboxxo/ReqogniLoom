"""P2.2 / m-4 — REST and MCP serialise a ``Document`` from one field map.

Before the fix the field list existed twice (``rest_api.views_entity_core
._document_to_dict`` and ``mcp_server.tools.document._document_to_dict``), so a
new Document field could appear on one transport only. Both now build on
``application.document_payload.document_fields``; each adds only what is
genuinely transport-side:

* REST: ``DocumentSerializer`` renders the temporal values as ISO-8601 and
  resolves ``status`` from the workflow engine.
* MCP: ``_document_to_dict`` adds ``status`` and renders the same four temporal
  fields through ``_render_document_temporal`` (``…Z`` for a UTC datetime, plain
  ISO for a ``date``) before the rest passes through ``transport_safe``.

The contract asserted here is the parity between those two payloads for one
real document — compared **byte-for-byte** for the temporal fields, against the
REST *serializer* output rather than a normalised copy of both sides. That
normalisation is exactly what let the ``…Z`` (REST) versus ``…+00:00`` (MCP)
divergence hide for a release. Service behaviour is covered elsewhere.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from application.document_payload import document_fields
from mcp_server.tools.document import _document_to_dict as mcp_document_to_dict
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Document
from rest_api.serializers_governance import DocumentSerializer
from rest_api.views_entity_core import _document_to_dict as rest_document_to_dict
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db

COLLECTION = "/api/v1/documents/"

#: The four fields the transports render; ``document_fields`` keeps them native.
TEMPORAL_KEYS = ("doc_date", "frozen_at", "created_at", "updated_at")


@pytest.fixture(autouse=True)
def _document_workflow(tenant, workspace):
    set_request_tenant(tenant.id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="document_default",
            item_type="Document",
            tenant_id=tenant.id,
        )
    finally:
        clear_request_tenant()


@pytest.fixture
def document(authed_client, tenant, workspace) -> Document:
    """One real document with a date and a custom field, read back from the DB."""
    response = authed_client.post(
        COLLECTION,
        {
            "workspace_id": str(workspace.id),
            "title": "Parity Spec",
            "kind": "Spec",
            "description": "Parity between the two transports",
            "body": "# Parity\n\nBody.",
            "doc_date": "2026-11-25",
            "custom_fields": {"traceability_ref": "REQ-L2-RA-001"},
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    created_id = response.json()["id"]

    set_request_tenant(tenant.id)
    try:
        return Document.objects.select_related("artifact").get(id=created_id)
    finally:
        clear_request_tenant()


def test_rest_and_mcp_payloads_differ_only_by_status(document, tenant):
    set_request_tenant(tenant.id)
    try:
        shared = document_fields(document)
        rest_map = rest_document_to_dict(document)
        mcp_map = mcp_document_to_dict(document)
        serialized = dict(DocumentSerializer(rest_map).data)
    finally:
        clear_request_tenant()

    # The shared map and the REST delegate are the same object shape.
    assert rest_map == shared

    # ``status`` is the only key the MCP transport adds to the shared map.
    assert set(mcp_map) - {"status"} == set(rest_map)
    assert "status" not in rest_map
    assert "status" not in shared
    assert isinstance(mcp_map["status"], str) and mcp_map["status"]

    # The four temporals are byte-for-byte identical to the REST serializer's
    # output — neither side is normalised here.
    for key in TEMPORAL_KEYS:
        assert mcp_map[key] == serialized[key], (
            f"{key!r} differs: REST {serialized[key]!r} vs MCP {mcp_map[key]!r}"
        )
    assert serialized["created_at"].endswith("Z"), serialized["created_at"]

    # Everything else matches too, with ``status`` supplied by each transport.
    assert serialized == mcp_map

    # ``custom_fields`` reaches both transports from the backing Artifact.
    assert rest_map["custom_fields"] == {"traceability_ref": "REQ-L2-RA-001"}
    assert mcp_map["custom_fields"] == rest_map["custom_fields"]


def test_shared_map_keeps_native_temporal_values(document):
    shared = document_fields(document)

    assert isinstance(shared["created_at"], datetime)
    assert isinstance(shared["updated_at"], datetime)
    assert isinstance(shared["doc_date"], date)
    assert not isinstance(shared["doc_date"], datetime)
    assert shared["frozen_at"] is None


def test_mcp_payload_renders_temporal_values_as_iso_strings(document, tenant):
    set_request_tenant(tenant.id)
    try:
        mcp_map = mcp_document_to_dict(document)
    finally:
        clear_request_tenant()

    assert mcp_map["doc_date"] == "2026-11-25"
    assert isinstance(mcp_map["created_at"], str)
    assert isinstance(mcp_map["updated_at"], str)
    # A UTC datetime is rendered with ``Z``, exactly like the DRF serializer —
    # not the ``+00:00`` spelling this transport used to publish.
    assert mcp_map["created_at"].endswith("Z"), mcp_map["created_at"]
    assert mcp_map["updated_at"].endswith("Z"), mcp_map["updated_at"]
    assert "+00:00" not in mcp_map["created_at"]
    assert mcp_map["frozen_at"] is None


def test_rest_serializer_adds_status_on_top_of_the_shared_map(document, tenant):
    """The REST wire shape is the shared map + engine-resolved ``status``."""
    set_request_tenant(tenant.id)
    try:
        mcp_map = mcp_document_to_dict(document)
        serialized = dict(DocumentSerializer(rest_document_to_dict(document)).data)
    finally:
        clear_request_tenant()

    assert set(serialized) == set(mcp_map)
    assert serialized["status"] == mcp_map["status"]
    assert serialized["doc_date"] == mcp_map["doc_date"]
    assert serialized["custom_fields"] == mcp_map["custom_fields"]
