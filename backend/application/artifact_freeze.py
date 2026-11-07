"""Workflow-driven write freeze for Requirements and ArchitectureElements (P4).

A state marked ``state_meta.freeze_on_enter`` locks the *content position* of
an artifact: it may not be moved, re-parented or (re-)allocated. This module is
the single read seam — the existing Document release freeze keeps its own
service, but both resolve the same ``freeze_on_enter`` flag from the workspace
workflow definition.

Decision E6: the **requirement's** state decides an allocation. A frozen
ArchitectureElement may itself not move, but it stays a valid allocation
target.
"""
from __future__ import annotations

from dataclasses import dataclass

from persistence.models import ArchitectureElement, Artifact, Requirement

_SUPPORTED_TYPES = frozenset({"Requirement", "ArchitectureElement"})
_FREEZE_STATE_META_KEY = "freeze_on_enter"


@dataclass(frozen=True)
class FreezeInfo:
    """The state name that freezes the artifact."""

    state_name: str


def _entity_id(artifact: Artifact, item_type: str):
    if item_type == "Requirement":
        return (
            Requirement.unscoped.filter(artifact_id=artifact.id)
            .values_list("id", flat=True)
            .first()
        )
    return (
        ArchitectureElement.unscoped.filter(artifact_id=artifact.id)
        .values_list("id", flat=True)
        .first()
    )


def is_frozen(artifact: Artifact) -> FreezeInfo | None:
    """Return the freeze state of *artifact*, or ``None`` when it is writable.

    Fails open (``None``) when the workflow definition or state cannot be read:
    the transition itself cannot happen without a definition, so there is
    nothing to gate and a lookup failure must not block an unrelated write.
    """
    item_type = getattr(artifact, "artifact_type", None)
    if item_type not in _SUPPORTED_TYPES:
        return None
    try:
        from workflow import state_reader
        from workflow.definition_store import get_state_meta
        from workflow.services import get_workflow_json

        entity_id = _entity_id(artifact, item_type)
        if entity_id is None:
            return None
        tenant_id = getattr(artifact, "tenant_id", None)
        current = state_reader.current_states(
            item_type, [entity_id], tenant_id=tenant_id
        ).get(str(entity_id))
        if current is None:
            return None
        workflow_json = get_workflow_json(artifact.workspace_id, item_type)
        meta = get_state_meta(workflow_json, current) or {}
        if meta.get(_FREEZE_STATE_META_KEY):
            return FreezeInfo(state_name=current)
    except Exception:  # noqa: BLE001 — fail open, see docstring
        return None
    return None
