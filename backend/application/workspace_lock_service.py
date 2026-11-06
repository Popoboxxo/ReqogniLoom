"""Batch lock read for the classic Requirement/Architecture trees (P4.4).

``GET /api/v1/workspaces/{id}/locks/?type=requirement|architecture`` answers the
one question the classic trees ask on load: *which of my nodes are frozen?*
The endpoint returns ``{"locks": {"<id>": "<state name>"}}`` and only the
artifacts whose **current workflow state** carries ``state_meta.freeze_on_enter``.

The read lives here rather than in ``rest_api.views`` because the REST adapter
performs no ORM access of its own (ADR-01, enforced by
``rest_api/tests/test_architecture.py``).

Cost is constant in the number of items: the freeze-triggering states of the
workspace's workflow definition are read once per item type and
``workflow.state_reader.current_states`` resolves every item's state in one
query. 10 items and 200 items therefore cost the same.

The freeze definition is deliberately **not** re-derived here. It is imported
from :mod:`application.allocation_view_service`, the same helper the allocation
view's ``locked`` column uses, so the two surfaces cannot drift apart.

ID SPACE — the keys are exactly the ids the two trees put on their
``WorkspaceTreeNode``, and the two trees differ:

* ``type=requirement`` → ``Requirement.id`` (the entity row id); the
  requirement tree renders ``id: req.id``.
* ``type=architecture`` → ``ArchitectureElement.id`` (the entity row id); the
  architecture tree renders ``id: el.id`` and translates to the backing
  Artifact id only for the move endpoint.

Neither id space is ``Artifact.id``.
"""
from __future__ import annotations

from uuid import UUID

from application.allocation_view_service import _frozen_states

__all__ = ["ITEM_TYPES", "get_workspace_locks"]

#: The public ``?type=`` values and the workflow item type each one addresses.
ITEM_TYPES: dict[str, str] = {
    "requirement": "Requirement",
    "architecture": "ArchitectureElement",
}


def get_workspace_locks(workspace_id: UUID, item_type: str) -> dict[str, str]:
    """Return ``{str(item_id): state}`` for every frozen item of *item_type*.

    Args:
        workspace_id: Workspace whose items are inspected.
        item_type: A value of :data:`ITEM_TYPES` (``requirement`` /
            ``architecture``). Callers validate it; an unknown key raises
            ``KeyError`` rather than silently returning an empty map.

    Returns:
        Mapping of the tree's node id to its current workflow state name,
        containing only ids whose state carries ``freeze_on_enter``.
    """
    resolved_type = ITEM_TYPES[item_type]
    frozen_states = _frozen_states(workspace_id)[resolved_type]

    from persistence.models import ArchitectureElement, Requirement
    from workflow import state_reader

    if resolved_type == "Requirement":
        item_ids = list(
            Requirement.objects.filter(workspace_id=workspace_id).values_list(
                "id", flat=True
            )
        )
    else:
        item_ids = list(
            ArchitectureElement.objects.filter(
                artifact__workspace_id=workspace_id
            ).values_list("id", flat=True)
        )

    states = state_reader.current_states(resolved_type, item_ids)
    return {
        str(item_id): state
        for item_id, state in states.items()
        if state in frozen_states
    }
