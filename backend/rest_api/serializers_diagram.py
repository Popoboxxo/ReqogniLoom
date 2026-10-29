"""
COMP-RA-002 DataSerializer — Diagram Canvas/Mermaid serializers.

leaf_id : COMP-RA-002
req_id  : REQ-L1-056 (Canvas), REQ-L1-057 (Mermaid),
          REQ-L2-DS-006 (CanvasEditor), REQ-L2-DS-007 (MermaidLiveRenderer)

Serializers for the Canvas and Mermaid sub-resources of the DiagramService
(IF-L1-058..061).  No direct ORM binding — pure adapter DTOs.

Architecture:
  docs/se/L1/Gesamtsystem/L2/DiagramServiceSystem/
  L2_DiagramServiceSystem_Architecture.md
"""
from __future__ import annotations

from typing import Any

from rest_framework import serializers

from diagram.node_graph import (
    EDGE_LINE_STYLES,
    EDGE_TYPES,
    HANDLE_POSITIONS,
    KNOWN_ARTIFACT_ENTITY_TYPES,
    NODE_TYPES,
    SCHEMA_VERSION,
    STYLE_ACCENTS,
)
from rest_api.serializers import UnknownFieldRejectionMixin

# ---------------------------------------------------------------------------
# Canvas Stroke Serializers (IF-L1-058, IF-L1-060)
# REQ-L1-056, REQ-L2-DS-006
# ---------------------------------------------------------------------------


class CanvasPointSerializer(serializers.Serializer):
    """Single point in a pen stroke."""

    x = serializers.FloatField()
    y = serializers.FloatField()


class CanvasStrokeElementSerializer(serializers.Serializer):
    """Single canvas element (pen stroke, shape, text, etc.)."""

    type = serializers.ChoiceField(
        choices=[
            "pen",
            "rect",
            "circle",
            "line",
            "text",
            "arrow",
            "connector",
        ],
    )
    color = serializers.CharField(required=False, default="#000000")
    width = serializers.FloatField(required=False, default=2)
    fill = serializers.CharField(required=False, default="none")
    opacity = serializers.FloatField(required=False, default=1.0)
    # Pen-specific
    points = CanvasPointSerializer(many=True, required=False)
    # Shape-specific
    x = serializers.FloatField(required=False, default=0)
    y = serializers.FloatField(required=False, default=0)
    height = serializers.FloatField(required=False, default=0)
    cx = serializers.FloatField(required=False, default=0)
    cy = serializers.FloatField(required=False, default=0)
    r = serializers.FloatField(required=False, default=0)
    x1 = serializers.FloatField(required=False, default=0)
    y1 = serializers.FloatField(required=False, default=0)
    x2 = serializers.FloatField(required=False, default=0)
    y2 = serializers.FloatField(required=False, default=0)
    # Text-specific
    content = serializers.CharField(required=False, default="", allow_blank=True)
    font_size = serializers.IntegerField(required=False, default=16)
    # Connector-specific
    source_id = serializers.CharField(required=False, default="", allow_blank=True)
    target_id = serializers.CharField(required=False, default="", allow_blank=True)
    id = serializers.CharField(required=False, default="", allow_blank=True)


class CanvasStrokeDataSerializer(
    UnknownFieldRejectionMixin, serializers.Serializer
):
    """Input serializer for canvas stroke data (IF-L1-058).

    The frontend pushes the complete stroke list on every auto-save.

    ``UnknownFieldRejectionMixin`` (#851) rejects request keys no declared
    field accepts instead of the DRF default of silently dropping them.
    """

    strokes = CanvasStrokeElementSerializer(many=True)
    width = serializers.IntegerField(required=False, default=800)
    height = serializers.IntegerField(required=False, default=600)
    # REQ-L2-CV-005: optional full canvas JSON (e.g. fabric.js). Additive —
    # legacy clients that send only strokes remain valid.
    canvas_json = serializers.JSONField(required=False, allow_null=True)


class CanvasStrokeResponseSerializer(serializers.Serializer):
    """Output serializer for canvas stroke retrieval (IF-L1-060)."""

    diagram_id = serializers.UUIDField()
    strokes = CanvasStrokeElementSerializer(many=True)
    width = serializers.IntegerField()
    height = serializers.IntegerField()
    svg = serializers.CharField()
    version_number = serializers.IntegerField(allow_null=True)
    # REQ-L2-CV-005: optional full canvas JSON (None for legacy versions).
    canvas_json = serializers.JSONField(required=False, allow_null=True)


# ---------------------------------------------------------------------------
# Mermaid Source Serializers (IF-L1-059, IF-L1-061)
# REQ-L1-057, REQ-L2-DS-007
# ---------------------------------------------------------------------------


class MermaidSourceSerializer(UnknownFieldRejectionMixin, serializers.Serializer):
    """Input serializer for Mermaid source code (IF-L1-059).

    ``UnknownFieldRejectionMixin`` (#851) rejects request keys no declared
    field accepts instead of the DRF default of silently dropping them.
    """

    source = serializers.CharField(allow_blank=True)


class MermaidSourceResponseSerializer(serializers.Serializer):
    """Output serializer for Mermaid source retrieval."""

    diagram_id = serializers.UUIDField()
    source = serializers.CharField()
    diagram_type = serializers.CharField()
    is_valid = serializers.BooleanField()
    error_message = serializers.CharField(allow_blank=True)


class MermaidPreviewResponseSerializer(serializers.Serializer):
    """Output serializer for Mermaid preview (IF-L1-061).

    Contains all data needed for the frontend live preview.
    """

    diagram_id = serializers.UUIDField()
    source = serializers.CharField()
    diagram_type = serializers.CharField()
    render_hints = serializers.JSONField(required=False, allow_null=True)
    fallback_mode = serializers.BooleanField()
    error_message = serializers.CharField(allow_blank=True)


# ---------------------------------------------------------------------------
# Node Graph Serializers (GH-353 Task 1) — documentation only
# REQ-L2-DS-002, PayloadFormat.NODE_GRAPH
# ---------------------------------------------------------------------------
#
# These serializers exist purely for drf-spectacular OpenAPI schema
# generation on the generic POST/PATCH /api/v1/diagrams/ intake path
# (content=<JSON string>). They import every enum/shape from
# diagram/node_graph.py rather than redeclaring them, so this file cannot
# become a second source of truth for the node_graph schema — the actual
# validation is performed exclusively by
# diagram.node_graph.validate_node_graph() via DiagramValidator.


class NodeGraphPositionSerializer(serializers.Serializer):
    """``Node.position`` — finite {x, y} coordinates."""

    x = serializers.FloatField()
    y = serializers.FloatField()


class NodeGraphSizeSerializer(serializers.Serializer):
    """``Node.size`` — optional finite {width, height} > 0."""

    width = serializers.FloatField()
    height = serializers.FloatField()


class NodeGraphNodeStyleSerializer(serializers.Serializer):
    """``Node.style`` — only ``accent`` is a recognised key."""

    accent = serializers.ChoiceField(choices=sorted(STYLE_ACCENTS), required=False)


class NodeGraphEdgeStyleSerializer(serializers.Serializer):
    """``Edge.style`` — only ``line`` is a recognised key."""

    line = serializers.ChoiceField(choices=sorted(EDGE_LINE_STYLES), required=False)


class NodeGraphArtifactRefSerializer(serializers.Serializer):
    """``Node.artifact_ref`` — link to an existing artifact entity.

    Existence of the referenced entity is verified at write time by the
    Task 3 reconciler, not by this documentation-only serializer.
    """

    entity_type = serializers.ChoiceField(choices=sorted(KNOWN_ARTIFACT_ENTITY_TYPES))
    id = serializers.UUIDField()


class NodeGraphNodeSerializer(serializers.Serializer):
    """A single node in a ``node_graph`` payload."""

    id = serializers.RegexField(regex=r"^[A-Za-z0-9_-]{1,64}$")
    type = serializers.ChoiceField(choices=sorted(NODE_TYPES))
    label = serializers.CharField(allow_blank=True, max_length=500)
    position = NodeGraphPositionSerializer()
    size = NodeGraphSizeSerializer(required=False)
    style = NodeGraphNodeStyleSerializer(required=False)
    artifact_ref = NodeGraphArtifactRefSerializer(required=False)
    parent_id = serializers.RegexField(
        regex=r"^[A-Za-z0-9_-]{1,64}$", required=False, allow_null=True
    )


class NodeGraphEdgeSerializer(serializers.Serializer):
    """A single edge in a ``node_graph`` payload."""

    id = serializers.RegexField(regex=r"^[A-Za-z0-9_-]{1,64}$")
    source = serializers.RegexField(regex=r"^[A-Za-z0-9_-]{1,64}$")
    target = serializers.RegexField(regex=r"^[A-Za-z0-9_-]{1,64}$")
    type = serializers.ChoiceField(choices=sorted(EDGE_TYPES))
    label = serializers.CharField(required=False, allow_blank=True, max_length=500)
    source_handle = serializers.ChoiceField(
        choices=sorted(HANDLE_POSITIONS), required=False, allow_null=True
    )
    target_handle = serializers.ChoiceField(
        choices=sorted(HANDLE_POSITIONS), required=False, allow_null=True
    )
    style = NodeGraphEdgeStyleSerializer(required=False)


class NodeGraphViewportSerializer(serializers.Serializer):
    """``NodeGraph.viewport`` — optional pan/zoom state."""

    x = serializers.FloatField(required=False, default=0)
    y = serializers.FloatField(required=False, default=0)
    zoom = serializers.FloatField(required=False, default=1)


class NodeGraphPayloadSerializer(serializers.Serializer):
    """Envelope for ``payload_format=node_graph`` (GH-353 Task 1).

    Documentation-only shape for the generic diagram intake/response body
    (``content`` is transported as a JSON-encoded string, not a nested
    object, on the actual REST endpoint).
    """

    schema_version = serializers.IntegerField(min_value=SCHEMA_VERSION, max_value=SCHEMA_VERSION)
    nodes = NodeGraphNodeSerializer(many=True)
    edges = NodeGraphEdgeSerializer(many=True)
    viewport = NodeGraphViewportSerializer(required=False)


# ---------------------------------------------------------------------------
# Contract serializers (#1388)
# ---------------------------------------------------------------------------
#
# Contract-only. ``DiagramViewSet``/``IcdViewSet`` deliberately have no
# ``serializer_class`` (SA-20: their handlers hand-build the response dicts
# against the DiagramService/IcdService DTOs), and that stays exactly as it
# is — these serializers transcribe the dicts for the generated document
# only. The version/diff/workflow entries are shared by BOTH viewsets, which
# is why they live here instead of in one of the two view modules.


class DiagramSerializer(serializers.Serializer):
    """List projection of one Diagram (``_diagram_to_dict``)."""

    id = serializers.CharField()
    name = serializers.CharField()
    diagram_type = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    workspace_id = serializers.CharField(required=False, allow_null=True)
    current_revision = serializers.IntegerField()
    created_at = serializers.CharField(required=False, allow_null=True)
    version_count = serializers.IntegerField()


class DiagramDetailSerializer(serializers.Serializer):
    """``retrieve`` projection: the list fields replaced by the current payload."""

    id = serializers.CharField()
    name = serializers.CharField()
    diagram_type = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    payload_format = serializers.CharField(required=False, allow_null=True)
    content = serializers.CharField(required=False, allow_null=True)
    version_number = serializers.IntegerField(required=False, allow_null=True)
    created_at = serializers.CharField(required=False, allow_null=True)


class DiagramListResponseSerializer(serializers.Serializer):
    """``StandardPagination`` envelope of ``GET /diagrams/``."""

    count = serializers.IntegerField()
    next = serializers.CharField(required=False, allow_null=True)
    previous = serializers.CharField(required=False, allow_null=True)
    page_size = serializers.IntegerField(required=False)
    max_page_size = serializers.IntegerField(required=False)
    results = DiagramSerializer(many=True)


class DiagramCreateRequestSerializer(serializers.Serializer):
    """Body of ``POST /diagrams/`` (read key-by-key off ``request.data``)."""

    name = serializers.CharField()
    diagram_type = serializers.CharField(required=False)
    payload_format = serializers.CharField(required=False)
    content = serializers.CharField(required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    workspace_id = serializers.UUIDField(required=False, allow_null=True)


class DiagramUpdateRequestSerializer(serializers.Serializer):
    """Body of ``PATCH /diagrams/{id}/`` — both keys are required by the view."""

    payload_format = serializers.CharField()
    content = serializers.CharField()


class DiagramVersionResponseSerializer(serializers.Serializer):
    """Body of ``PATCH /diagrams/{id}/`` — the newly appended diagram version."""

    version_number = serializers.IntegerField()
    payload_format = serializers.CharField()
    content = serializers.CharField()


class ArtifactVersionEntrySerializer(serializers.Serializer):
    """One ``ArtifactDiffService.list_versions`` row (#272 contract)."""

    version = serializers.IntegerField()
    label = serializers.CharField()
    modified_at = serializers.CharField(required=False, allow_null=True)
    content_available = serializers.BooleanField()
    is_creation_baseline = serializers.BooleanField()


class ArtifactDiffFieldSerializer(serializers.Serializer):
    """One field-level diff entry of ``ArtifactDiffService.diff``."""

    name = serializers.CharField()
    status = serializers.ChoiceField(
        choices=["added", "removed", "modified", "unchanged"]
    )
    to = serializers.JSONField(required=False)
    #: Unified diff lines, only for changed text fields.
    lines = serializers.ListField(child=serializers.CharField(), required=False)


#: The previous value of a changed field is published as ``from`` — a Python
#: keyword, so it cannot be declared in the class body. Added through DRF's
#: ``_declared_fields`` seam (what the metaclass itself writes) instead.
ArtifactDiffFieldSerializer._declared_fields["from"] = serializers.JSONField(
    required=False
)


class ArtifactDiffResponseSerializer(serializers.Serializer):
    """Body of ``GET /diagrams/{id}/diff/`` (``ArtifactDiffService.diff``)."""

    from_version = serializers.IntegerField()
    to_version = serializers.IntegerField()
    entity_type = serializers.CharField()
    fields = ArtifactDiffFieldSerializer(many=True)
    note = serializers.CharField(required=False)


class WorkflowTransitionsResponseSerializer(serializers.Serializer):
    """``GET …/transitions/`` — current state plus the allowed moves.

    Shared contract of :class:`rest_api.mixins.workflow_transitions.
    WorkflowTransitionsMixin`, published by both the Diagram and the ICD
    surface.
    """

    current_state = serializers.CharField(required=False, allow_null=True)
    version = serializers.IntegerField(required=False, allow_null=True)
    states = serializers.ListField(child=serializers.CharField())
    allowed_transitions = serializers.ListField(child=serializers.JSONField())
    proposed_by = serializers.CharField(required=False, allow_null=True)


class WorkflowTransitionRequestSerializer(serializers.Serializer):
    """Body of ``POST …/transitions/``."""

    target_state = serializers.CharField()
    change_reason = serializers.CharField(required=False, allow_blank=True)
    credential = serializers.CharField(required=False, allow_blank=True)
    #: WorkflowItemState revision, NOT the entity ETag (see the mixin docstring).
    expected_version = serializers.IntegerField(required=False, allow_null=True)


class WorkflowTransitionResultSerializer(serializers.Serializer):
    """``POST …/transitions/`` / ``POST …/reactivate/`` success envelope.

    ``id`` is the URL ``pk`` as a string; ``version`` is the workflow revision
    AFTER the transition (``null`` when no ``WorkflowItemState`` row exists).
    """

    id = serializers.CharField()
    previous_state = serializers.CharField(required=False, allow_null=True)
    new_state = serializers.CharField(required=False, allow_null=True)
    version = serializers.IntegerField(required=False, allow_null=True)
    #: ViewSets that embed the refreshed entity spread its keys in at top level.
    #: Diagram and Icd do not, so no additional keys are declared here.


class WorkflowHistoryEntrySerializer(serializers.Serializer):
    """One ``GET …/workflow-history/`` audit row."""

    id = serializers.CharField()
    from_state = serializers.CharField(required=False, allow_null=True)
    to_state = serializers.CharField()
    actor = serializers.CharField(required=False, allow_null=True)
    change_reason = serializers.CharField(required=False, allow_blank=True)
    transitioned_at = serializers.CharField()
    sealed = serializers.BooleanField()

__all__ = [
    "ArtifactDiffFieldSerializer",
    "ArtifactDiffResponseSerializer",
    "ArtifactVersionEntrySerializer",
    "CanvasPointSerializer",
    "CanvasStrokeDataSerializer",
    "CanvasStrokeElementSerializer",
    "CanvasStrokeResponseSerializer",
    "MermaidPreviewResponseSerializer",
    "MermaidSourceResponseSerializer",
    "MermaidSourceSerializer",
    "NodeGraphArtifactRefSerializer",
    "NodeGraphEdgeSerializer",
    "NodeGraphEdgeStyleSerializer",
    "NodeGraphNodeSerializer",
    "NodeGraphNodeStyleSerializer",
    "NodeGraphPayloadSerializer",
    "NodeGraphPositionSerializer",
    "NodeGraphSizeSerializer",
    "NodeGraphViewportSerializer",
    "DiagramCreateRequestSerializer",
    "DiagramDetailSerializer",
    "DiagramListResponseSerializer",
    "DiagramSerializer",
    "DiagramUpdateRequestSerializer",
    "DiagramVersionResponseSerializer",
    "WorkflowHistoryEntrySerializer",
    "WorkflowTransitionRequestSerializer",
    "WorkflowTransitionResultSerializer",
    "WorkflowTransitionsResponseSerializer",
]
