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

import logging
from dataclasses import dataclass

from persistence.models import ArchitectureElement, Artifact, Requirement

logger = logging.getLogger(__name__)

_SUPPORTED_TYPES = frozenset({"Requirement", "ArchitectureElement"})
_FREEZE_STATE_META_KEY = "freeze_on_enter"


class ArtifactFreezeLookupError(RuntimeError):
    """Raised when the workflow state needed for a freeze check cannot be read.

    APP-002 fail-closed hardening: this seam used to swallow *every* exception
    and answer ``None`` (writable), so a DB/cache outage silently disabled the
    freeze gate. A genuine lookup failure is now logged with
    :func:`logging.exception` and raised as this typed error, which propagates
    through the three callers (``artifact_fields_update``, ``artifact_service``,
    ``trace_link_service``) and blocks the write.

    The legitimate "nothing to gate" cases — unsupported artifact type, no
    backing Requirement/ArchitectureElement row, or an item with no current
    workflow state — still return ``None`` (writable). Only real lookup
    failures raise. Chosen over reusing ``WorkflowFrozenError`` because that
    error models a *known frozen state* and requires a ``state_name``, which
    does not exist when the lookup itself failed.
    """


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

    Legitimate "nothing to gate" cases return ``None`` (writable): an
    unsupported artifact type, no backing Requirement/ArchitectureElement row,
    or an item with no current workflow state. A *genuine lookup failure*
    (APP-002) is different — it is logged with ``logger.exception`` and raised
    as :class:`ArtifactFreezeLookupError` so callers fail closed instead of
    treating an unreadable freeze gate as "writable". All three call sites rely
    on ``None`` meaning writable; that contract is preserved.
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
    except Exception as exc:  # re-raised below — fail closed (APP-002)
        logger.exception(
            "artifact_freeze: freeze-state lookup failed for artifact=%s "
            "type=%s — failing closed",
            getattr(artifact, "id", None),
            item_type,
        )
        raise ArtifactFreezeLookupError(
            f"Could not resolve workflow freeze state for artifact "
            f"{getattr(artifact, 'id', None)}: {exc}"
        ) from exc
    return None
