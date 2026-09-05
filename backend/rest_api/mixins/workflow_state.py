"""Batched ``status`` field backed by the workflow engine.

Datenmodell-Konsolidierung Phase 0. Replaces the denormalized ``status`` model
column as the serializer's *primary* data source while keeping the wire key and
its value vocabulary identical (Decision D-1) — the column was a same-transaction
mirror, so no response value changes. Falls back to the column itself for items
the engine does not track (no ``WorkflowItemState`` row — e.g. Goal/MainGoal,
which have no state backfill, or any item created in a definition-less
workspace), so Phase 0 stays value-neutral and reversible until the column is
actually dropped in Phase 1.

Task 12: the column is now dropped. ``getattr(row, "status", "")`` never
raised (it degrades gracefully to the default), but with no column left it
would silently return ``""`` for every untracked row across every REST list/
detail endpoint using this mixin instead of a meaningful state — a much
broader, harder-to-notice regression than a crash. The fallback below now
resolves ``workflow.state_reader.initial_state`` per item type instead
(documented, reviewed data-loss tradeoff, see the Task 12 report, Finding 2).

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
        """Return the item's current workflow state.

        Task 12: the ``status`` column is dropped. Falls back to
        ``workflow_item_type``'s preset initial state when the engine has no
        ``WorkflowItemState`` row for it — Goal/MainGoal have no state
        backfill at all, and any item created in a definition-less workspace
        is state-less too. Without this fallback those rows would silently
        regress to ``""`` (documented, reviewed data-loss tradeoff for the
        legacy value itself, see the Task 12 report Finding 2 — but an empty
        string is not an acceptable *wire* value, so the initial state is
        used instead).
        """
        engine_state = self._workflow_state_map().get(str(_row_id(obj)))
        if engine_state is not None:
            return engine_state
        return state_reader.initial_state(self.workflow_item_type)

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
        elif isinstance(instance, dict):
            # Every real call site (rest_api/views.py) hands the mixin a
            # ``_dto_from_orm``-style dict, not the ORM row itself — checked
            # before the generic __iter__ branch below because a dict is
            # itself iterable (over its keys), which would otherwise be
            # misread as a row collection.
            ids = [_row_id(instance)]
        elif hasattr(instance, "__iter__") and not isinstance(instance, (str, bytes)):
            # A QuerySet/list is already fully evaluated at this point: DRF's
            # ListSerializer.to_representation iterates it before the first
            # child call, which populates _result_cache. Each row may itself
            # be a dict (many=True over DTO dicts) or an ORM object.
            ids = [_row_id(row) for row in instance]
        else:
            ids = [_row_id(instance)]

        cached = state_reader.current_states(self.workflow_item_type, ids)
        self._workflow_state_cache = cached
        return cached


def _row_id(row: Any) -> Any:
    """Extract the identifying key from a serializer row.

    Every real call site (``rest_api/views.py``) hands the serializer a
    ``_dto_from_orm``-style ``dict`` with an ``"id"`` key, not the ORM row
    itself — only test doubles use ``.pk``.
    """
    return row.get("id") if isinstance(row, dict) else row.pk


__all__ = ["WorkflowStateSerializerMixin"]
