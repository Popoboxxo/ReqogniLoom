"""
ARCH-L1-006 BaselineService — DRF serializers for scope-preview.

leaf_id: COMP-BL-005
req_id:  REQ-L1-049

Serializers are intentionally minimal: the preview payload is a tiny
read-only structure, so we use plain ``serializers.Serializer`` rather than
a ModelSerializer. This keeps the schema surface explicit and avoids any
leakage of internal model state.
"""
from __future__ import annotations

from rest_framework import serializers


class ScopePreviewItemSerializer(serializers.Serializer):
    """One item in the scope preview sample (REQ-L1-049)."""

    id = serializers.CharField()
    title = serializers.CharField()
    type = serializers.CharField()
    entity_type = serializers.CharField(required=False, default="item")


class ScopePreviewSerializer(serializers.Serializer):
    """Read-only payload for the scope-preview endpoint (REQ-L1-049)."""

    scope = serializers.CharField()
    count = serializers.IntegerField()
    sample = ScopePreviewItemSerializer(many=True)


__all__ = [
    "ScopePreviewItemSerializer",
    "ScopePreviewSerializer",
]
