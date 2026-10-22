"""OpenAPI shapes for the memory endpoints typed for #1388.

The memory views return dicts assembled by
:class:`application.memory_entry_service.MemoryEntryService` (``_view`` /
``search`` / ``envelope``). The serializers below transcribe that shape for the
generated contract only; runtime code keeps returning the service's dicts. Only
the semantic-search endpoint is typed here — the remaining memory endpoints are
still intentionally untyped and listed in
``rest_api.schema.UNTYPED_VIEW_ALLOWLIST``.
"""
from __future__ import annotations

from rest_framework import serializers

__all__ = ["MemorySearchResponseSerializer", "MemorySearchItemSerializer"]


class MemorySearchItemSerializer(serializers.Serializer):
    """One semantic-search hit (``MemoryEntryService._view``)."""

    entry_id = serializers.CharField(allow_null=True)
    content = serializers.CharField()
    scope = serializers.CharField()
    workspace_id = serializers.CharField(required=False, allow_null=True)
    user_id = serializers.CharField(required=False, allow_null=True)
    artifact_id = serializers.CharField(required=False, allow_null=True)
    entity_type = serializers.CharField(required=False, allow_blank=True)
    contributor_user_id = serializers.CharField(required=False, allow_null=True)
    source_event_id = serializers.CharField(required=False, allow_null=True)
    source_session_id = serializers.CharField(required=False, allow_null=True)
    confidence = serializers.FloatField(required=False, allow_null=True)
    language = serializers.CharField(required=False, allow_blank=True)
    created_at = serializers.DateTimeField(required=False, allow_null=True)
    superseded_by = serializers.CharField(required=False, allow_null=True)
    backend_ref = serializers.CharField(required=False, allow_null=True)
    # Health envelope copied onto every item.
    backend = serializers.CharField(required=False)
    ok = serializers.BooleanField(required=False)
    detail = serializers.CharField(required=False, allow_null=True)
    degraded = serializers.BooleanField(required=False)
    digest_available = serializers.BooleanField(required=False)
    ask_available = serializers.BooleanField(required=False)
    derivation_status = serializers.CharField(required=False)


class MemorySearchResponseSerializer(serializers.Serializer):
    """``GET /api/v1/workspaces/{workspace_id}/memory/search/`` body."""

    items = MemorySearchItemSerializer(many=True)
    query = serializers.CharField()
    scopes = serializers.ListField(child=serializers.CharField())
    backend = serializers.CharField(required=False)
    ok = serializers.BooleanField(required=False)
    detail = serializers.CharField(required=False, allow_null=True)
    degraded = serializers.BooleanField(required=False)
    digest_available = serializers.BooleanField(required=False)
    ask_available = serializers.BooleanField(required=False)
    derivation_status = serializers.CharField(required=False)
