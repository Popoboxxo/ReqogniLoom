"""Batched ``status`` field backed by the workflow engine.

Datenmodell-Konsolidierung Phase 0. Replaces the denormalized ``status`` model
column as the serializer's data source while keeping the wire key and its value
vocabulary identical (Decision D-1) — the column was a same-transaction mirror,
so no response value changes.

The resolution is batched deliberately. DRF builds a *single* child serializer
for ``many=True`` and calls ``get_status`` once per row; resolving per row would
turn every list endpoint into an N+1. The child caches the whole mapping on
first access, so a list of any size costs one query.
"""
from __future__ import annotations

from typing import Any, ClassVar

from rest_framework import serializers

from workflow import state_reader


class WorkflowStateSerializerMixin(serializers.Serializer):
    """Adds a read-only, engine-resolved ``status`` field.

    Subclasses must set :attr:`workflow_item_type` to the entity type string
    used in ``WorkflowItemState.item_type`` (e.g. ``"Requirement"``).

    Inherits from ``serializers.Serializer`` (rather than being a plain mixin)
    because DRF's ``SerializerMetaclass`` only merges ``_declared_fields`` from
    bases that already carry that attribute — a plain-object mixin's ``status``
    field would silently be dropped from every concrete serializer. Safe to mix
    into ``ModelSerializer`` subclasses too: both ultimately derive from
    ``Serializer``, so Python resolves the diamond MRO without conflict.
    """

    #: ``WorkflowItemState.item_type`` value for this serializer's model.
    workflow_item_type: ClassVar[str] = ""

    status = serializers.SerializerMethodField()

    def get_status(self, obj: Any) -> str:
        """Return the item's current workflow state, or ``""`` if untracked."""
        return self._workflow_state_map().get(str(obj.pk), "")

    def _workflow_state_map(self) -> dict[str, str]:
        cached = getattr(self, "_workflow_state_cache", None)
        if cached is not None:
            return cached

        assert self.workflow_item_type, (
            f"{type(self).__name__} uses WorkflowStateSerializerMixin but does "
            "not set workflow_item_type"
        )

        # For many=True the ListSerializer parent holds the full instance set;
        # for a single object `self` does.
        root = self.parent if isinstance(self.parent, serializers.ListSerializer) else self
        instance = root.instance

        if instance is None:
            ids: list[Any] = []
        elif hasattr(instance, "__iter__") and not isinstance(instance, (str, bytes)):
            # A QuerySet is already fully evaluated at this point: DRF's
            # ListSerializer.to_representation iterates it before the first
            # child call, which populates _result_cache.
            ids = [row.pk for row in instance]
        else:
            ids = [instance.pk]

        cached = state_reader.current_states(self.workflow_item_type, ids)
        self._workflow_state_cache = cached
        return cached


__all__ = ["WorkflowStateSerializerMixin"]
