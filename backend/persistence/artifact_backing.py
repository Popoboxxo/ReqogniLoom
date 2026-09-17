"""Shared Artifact-backing helper (Datenmodell-Konsolidierung Phase 3, spec §4).

Every specialised artifact table owns exactly one ``persistence.Artifact`` row,
which is what makes it a valid TraceLink endpoint, a baseline-diff subject and
an interview target. Four types acquired that backing at different times with
four slightly different code paths; this module is the one implementation all of
them use.

Lives in Layer 0 on purpose: ``diagram``, ``icd`` and ``persistence`` itself all
need it, and Layer 0 is the only layer all three may import.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from django.db import models, transaction

from persistence.models import Artifact


class ArtifactBackingError(RuntimeError):
    """An entity cannot be given a backing Artifact row."""


#: ``Artifact.artifact_type`` -> ``(app_label, model_name)`` of the specialised
#: table that owns it. The single registry for "which table backs this type" —
#: used by ``check_artifact_backing``, by ``workflow.services.outdated_item_ids``
#: and by the version service. Adding a new artifact type means adding one line
#: here; nothing else has to learn about it.
ARTIFACT_TYPE_MODELS: dict[str, tuple[str, str]] = {
    "Requirement": ("persistence", "Requirement"),
    "StakeholderNeed": ("persistence", "StakeholderNeed"),
    "ArchitectureElement": ("persistence", "ArchitectureElement"),
    "TestCase": ("persistence", "TestCase"),
    "GlossaryTerm": ("persistence", "GlossaryTerm"),
    "Adr": ("persistence", "Adr"),
    "Risk": ("persistence", "Risk"),
    "Issue": ("persistence", "Issue"),
    "Goal": ("persistence", "Goal"),
    "MainGoal": ("persistence", "MainGoal"),
    "ChangeRequest": ("persistence", "ChangeRequest"),
    "Diagram": ("diagram", "Diagram"),
    "Icd": ("icd", "Icd"),
}


def model_for(artifact_type: str):
    """Return the specialised model class backing *artifact_type*.

    Raises:
        KeyError: *artifact_type* is not a backed type.
    """
    from django.apps import apps

    app_label, model_name = ARTIFACT_TYPE_MODELS[artifact_type]
    return apps.get_model(app_label, model_name)


def ensure_artifact(
    entity: models.Model,
    *,
    artifact_type: str,
    workspace_id: UUID | None,
    field_name: str = "artifact",
) -> UUID:
    """Return *entity*'s backing Artifact id, creating the row if absent.

    Idempotent and race-safe: the entity row is re-read under
    ``select_for_update`` whenever the backing is ambiguous, so two concurrent
    callers cannot both insert an Artifact and orphan one of them.

    Must be called inside an open transaction — ``select_for_update`` requires
    one, and the Artifact insert must roll back with the caller's operation.

    Args:
        entity:        The specialised row (Diagram, Icd, GlossaryTerm, ...).
        artifact_type: Value for ``Artifact.artifact_type``, e.g. ``"Icd"``.
        workspace_id:  Owning workspace. ``Artifact.workspace`` is not
                       nullable, so ``None`` is a hard error.
        field_name:    Name of the OneToOne field on *entity*.

    Returns:
        The UUID of the (possibly newly created) Artifact.

    Raises:
        ArtifactBackingError: *workspace_id* is ``None``, or this function is
            called outside an open transaction.
    """
    existing = getattr(entity, f"{field_name}_id", None)
    if existing is not None:
        return existing

    if workspace_id is None:
        raise ArtifactBackingError(
            f"{type(entity).__name__} {entity.pk} has no workspace; an Artifact "
            "row requires a non-null workspace and cannot be created."
        )

    if not transaction.get_connection().in_atomic_block:
        raise ArtifactBackingError(
            "ensure_artifact must run inside an atomic block so the Artifact "
            "row rolls back with the caller's operation."
        )

    locked = type(entity).objects.select_for_update().get(pk=entity.pk)
    locked_id = getattr(locked, f"{field_name}_id", None)
    if locked_id is not None:
        setattr(entity, f"{field_name}_id", locked_id)
        return locked_id

    artifact = Artifact.objects.create(
        artifact_type=artifact_type,
        tenant=locked.tenant,
        workspace_id=workspace_id,
    )
    setattr(locked, field_name, artifact)
    locked.save(update_fields=[field_name, "modified_at"])
    setattr(entity, field_name, artifact)
    return artifact.id


def artifact_id_of(entity: Any, field_name: str = "artifact") -> UUID | None:
    """Return *entity*'s backing Artifact id without creating one."""
    return getattr(entity, f"{field_name}_id", None)


__all__ = [
    "ARTIFACT_TYPE_MODELS",
    "ArtifactBackingError",
    "artifact_id_of",
    "ensure_artifact",
    "model_for",
]
