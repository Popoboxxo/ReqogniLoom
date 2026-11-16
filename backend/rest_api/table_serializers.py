"""Wire serializers for the artifact table (Tabellenansicht S1, Task 1.6).

They exist for two reasons: a ``Serializer`` is what drf-spectacular publishes
as the operation's response schema (the OpenAPI completeness gate rejects an
operation whose body cannot be derived), and it documents the frozen row shape
without the view re-stating it.

The rows themselves are built in Layer 2
(:meth:`application.table_query_service.TableQueryService.serialize_rows`) — a
serializer here would have to re-implement owner/status/extended resolution and
drift from ``saved-views/<id>/apply/``, which returns the same rows.
"""
from __future__ import annotations

from rest_framework import serializers

__all__ = ["TablePageSerializer", "TableRowSerializer"]


class TableRowSerializer(serializers.Serializer):
    """One table row (spec §4.1)."""

    id = serializers.UUIDField(
        help_text="Typed entity id (e.g. the Requirement id)."
    )
    artifact_id = serializers.UUIDField(
        help_text="Backing pl_artifact id — the write target of a bulk request."
    )
    item_type = serializers.CharField()
    version = serializers.IntegerField(
        help_text="Entity optimistic-lock counter the row was read at."
    )
    values = serializers.DictField(
        help_text="Attribute values keyed by attribute name (JSON primitives)."
    )
    locked = serializers.DictField(
        allow_null=True,
        help_text="{'state': '<state name>'} when a freeze state holds the row.",
    )


class TablePageSerializer(serializers.Serializer):
    """Paginated table page (``StandardPagination`` envelope)."""

    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    page_size = serializers.IntegerField()
    max_page_size = serializers.IntegerField()
    results = TableRowSerializer(many=True)
