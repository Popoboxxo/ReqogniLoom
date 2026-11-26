"""Transport-neutral field map of the ``Document`` artifact (P2.2 / m-4).

``Document`` was serialised twice — once by
``rest_api.views_entity_core._document_to_dict`` and once by
``mcp_server.tools.document._document_to_dict`` — so a field added to one
transport silently drifted from the other (the review's finding m-4). This
module owns the single canonical field map; both transports consume it.

What stays transport-side, deliberately:

* **Temporal rendering.** ``doc_date``/``frozen_at``/``created_at``/
  ``updated_at`` are returned as **native** ``date``/``datetime`` values. The
  DRF ``DocumentSerializer`` renders them as ISO-8601 with a ``Z`` suffix for a
  UTC datetime; the MCP tool layer renders the same four keys through its own
  ``_render_document_temporal`` helper and therefore emits the **identical**
  byte form (the ``…+00:00`` spelling the MCP surface used to publish is gone).
* **The lifecycle ``status``.** ``Document`` has no lifecycle column (ADR-026
  R2); the state is resolved by the workflow engine. REST's
  ``WorkflowStateSerializerMixin`` resolves it from the serializer instance,
  the MCP tool from ``resolve_engine_status`` with its batched ``status_map``.
  The key is therefore absent here and added by each transport.

The map is a plain ``dict`` — not a model query, not a service call — so both
layers can keep constructing it from a row they already hold (ADR-01: no ORM
access from the transport layer, and none is added here).
"""
from __future__ import annotations

from typing import Any

__all__ = ["document_fields"]


def _custom_fields(document: Any) -> dict[str, Any]:
    """Return ``custom_fields`` from the backing ``Artifact`` (REQ-L2-AS-037).

    The extended attributes live on ``Artifact.custom_fields`` and every
    artifact-backed entity reaches them through its ``artifact`` relation.
    Missing/NULL/non-dict values normalise to ``{}`` so both transports publish
    the same stable shape.
    """
    artifact = getattr(document, "artifact", None)
    source = artifact if artifact is not None else document
    custom_fields = getattr(source, "custom_fields", None)
    return custom_fields if isinstance(custom_fields, dict) else {}


def document_fields(document: Any) -> dict[str, Any]:
    """Return the transport-neutral field map of one ``Document`` row.

    Args:
        document: A ``persistence.models.Document`` instance (or any object
            exposing the same attributes).

    Returns:
        A dict whose keys and values are exactly what the REST helper produced
        before this module existed — minus ``status``, which stays a transport
        concern (see the module docstring). Temporal values are native
        ``date``/``datetime`` objects; no ISO conversion happens here.

    The wire key for the house ``modified_at`` column is ``updated_at``: the
    contract matches every other artifact even though ``Document`` does not
    define its own ``updated_at`` column.
    """
    return {
        "id": str(document.id),
        "workspace_id": str(document.workspace_id),
        "artifact_id": (
            str(document.artifact_id)
            if getattr(document, "artifact_id", None)
            else None
        ),
        "uid": getattr(document, "uid", None),
        "title": document.title,
        "kind": document.kind,
        "description": getattr(document, "description", ""),
        "body": getattr(document, "body", ""),
        "doc_date": getattr(document, "doc_date", None),
        "frozen_at": getattr(document, "frozen_at", None),
        "frozen_fields": list(getattr(document, "frozen_fields", None) or []),
        # Phase G / #1374 S3: dual-source and projection bookkeeping (read-only).
        "owner_mode": getattr(document, "owner_mode", "loom"),
        "source_path": getattr(document, "source_path", ""),
        "source_sha256": getattr(document, "source_sha256", ""),
        "projection_mode": getattr(document, "projection_mode", "none"),
        "projected_sha256": getattr(document, "projected_sha256", ""),
        "projected_version": getattr(document, "projected_version", None),
        "custom_fields": _custom_fields(document),
        "version": document.version,
        "created_at": document.created_at,
        "updated_at": document.modified_at,
    }
