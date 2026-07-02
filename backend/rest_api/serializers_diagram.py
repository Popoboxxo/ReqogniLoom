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


class CanvasStrokeDataSerializer(serializers.Serializer):
    """Input serializer for canvas stroke data (IF-L1-058).

    The frontend pushes the complete stroke list on every auto-save.
    """

    strokes = CanvasStrokeElementSerializer(many=True)
    width = serializers.IntegerField(required=False, default=800)
    height = serializers.IntegerField(required=False, default=600)


class CanvasStrokeResponseSerializer(serializers.Serializer):
    """Output serializer for canvas stroke retrieval (IF-L1-060)."""

    diagram_id = serializers.UUIDField()
    strokes = CanvasStrokeElementSerializer(many=True)
    width = serializers.IntegerField()
    height = serializers.IntegerField()
    svg = serializers.CharField()
    version_number = serializers.IntegerField(allow_null=True)


# ---------------------------------------------------------------------------
# Mermaid Source Serializers (IF-L1-059, IF-L1-061)
# REQ-L1-057, REQ-L2-DS-007
# ---------------------------------------------------------------------------


class MermaidSourceSerializer(serializers.Serializer):
    """Input serializer for Mermaid source code (IF-L1-059)."""

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


__all__ = [
    "CanvasPointSerializer",
    "CanvasStrokeElementSerializer",
    "CanvasStrokeDataSerializer",
    "CanvasStrokeResponseSerializer",
    "MermaidSourceSerializer",
    "MermaidSourceResponseSerializer",
    "MermaidPreviewResponseSerializer",
]
