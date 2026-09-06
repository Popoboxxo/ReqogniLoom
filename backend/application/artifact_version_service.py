"""COMP-AS-0xx ArtifactVersionService — the single content-revision store.

Datenmodell-Konsolidierung Phase 5 (spec §6, Decision D-4). Replaces
DiagramVersion, IcdVersion and GlossaryTermVersion with one append-only
snapshot table shared by every artifact type, and gives the eight types that
had *no* retrievable history (ADR-AS-019 single-row model, issue #213) a real
one for the first time.

Not to be confused with :mod:`audit`, which stays an append-only *operation*
trail (who did what, when), or with :mod:`baseline`, which snapshots a whole
workspace at a point in time. This module answers "what did this one artifact
look like at revision N".
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from django.db import transaction
from django.db.models import Max

from auth_tenancy.context import AuthContext
from persistence.models import Artifact, ArtifactVersion

from application.base import NotFoundError, ServiceBase


def snapshot_fields(entity: Any, item_type: str) -> Dict[str, Any]:
    """Build a revision payload from the diffable field list for *item_type*.

    Reads ``artifact_diff_service._ENTITY_FIELDS`` so the fields that get
    stored and the fields that get diffed are the same set by construction —
    a snapshot that omits a diffed field would silently render as "changed to
    empty" on every comparison.

    Unknown types return ``{}``: recording nothing is correct for a type that
    the diff engine cannot render anyway.

    Args:
        entity:    The ORM row (or any object exposing the named attributes).
        item_type: Key into ``_ENTITY_FIELDS``, e.g. ``"Requirement"``.

    Returns:
        Mapping of field name -> current value. Missing attributes read as
        ``None`` rather than raising, so a partially-populated object still
        yields a well-shaped snapshot.
    """
    # Imported lazily: artifact_diff_service imports application.models, which
    # pulls in the whole service package — a module-level import here would
    # make the version store depend on the diff engine's import graph.
    from application.artifact_diff_service import _ENTITY_FIELDS

    fields = _ENTITY_FIELDS.get(item_type, [])
    return {name: getattr(entity, name, None) for name in fields}


def lineage_anchor_artifact_id(
    model: Any,
    lineage_id: Optional[UUID] = None,
    *,
    workspace_id: Optional[UUID] = None,
) -> Optional[UUID]:
    """Return the ``artifact_id`` of a lineage's first version.

    Goal and MainGoal are immutable-row-per-version: every edit writes a new
    row *and a new Artifact* (``goal_service.create_version``). Anchoring their
    revisions on the ``sequence_number == 1`` row's Artifact makes the whole
    lineage readable through the same ``list_revisions``/``diff`` pair as every
    other artifact type, instead of N artifacts holding one revision each.

    The two types scope their lineage differently, so exactly one of the two
    scoping arguments applies:

    * ``Goal`` groups versions by ``lineage_id`` (per-lineage sequence).
    * ``MainGoal`` has no ``lineage_id`` column at all — its lineage *is* the
      workspace, and ``sequence_number`` is unique per workspace
      (``uq_main_goal_workspace_sequence``).

    Args:
        model:        ``Goal`` or ``MainGoal`` model class.
        lineage_id:   The lineage to anchor on (Goal).
        workspace_id: The owning workspace (MainGoal).

    Returns:
        The anchor Artifact id, or ``None`` if the scope has no version 1
        (possible only for pre-lineage legacy rows).
    """
    filters: Dict[str, Any] = {"sequence_number": 1}
    if lineage_id is not None:
        filters["lineage_id"] = lineage_id
    if workspace_id is not None:
        filters["workspace_id"] = workspace_id
    return (
        model.objects.filter(**filters)
        .values_list("artifact_id", flat=True)
        .first()
    )


class ArtifactVersionService(ServiceBase):
    """Append-only content revisions for any Artifact."""

    @transaction.atomic
    def record(
        self,
        artifact_id: UUID,
        payload: Dict[str, Any],
        ctx: AuthContext,
        *,
        change_reason: str = "",
        revision: Optional[int] = None,
    ) -> int:
        """Append a new revision and return its number.

        The next number is allocated while holding a row lock on the Artifact,
        so two concurrent writers cannot both compute the same value and hit
        the ``uq_artifact_version_revision`` constraint.

        Args:
            artifact_id:   Artifact whose content is being snapshotted.
            payload:       Full field snapshot (not a delta).
            ctx:           Resolved AuthContext.
            change_reason: Optional reason, mirrored from the write request.
            revision:      Explicit revision number. Leave ``None`` to
                auto-allocate ``MAX(revision) + 1`` — the behaviour every
                in-place type relies on. The immutable-row-per-version types
                (Goal, MainGoal) pass their own ``sequence_number`` instead,
                because their revision numbering is owned by the lineage and
                must stay in that namespace.

        Returns:
            The new revision number (1 for the first snapshot).

        Raises:
            NotFoundError: no such Artifact in this tenant.
        """
        self._set_tenant_context(ctx)

        artifact = (
            Artifact.objects.select_for_update().filter(pk=artifact_id).first()
        )
        if artifact is None:
            raise NotFoundError(f"Artifact {artifact_id} not found")

        if revision is None:
            current_max = (
                ArtifactVersion.objects.filter(artifact_id=artifact_id).aggregate(
                    highest=Max("revision")
                )["highest"]
                or 0
            )
            revision = current_max + 1

        ArtifactVersion.objects.create(
            tenant=artifact.tenant,
            artifact=artifact,
            revision=revision,
            payload=payload,
            change_reason=change_reason,
        )
        return revision

    def list_revisions(
        self, artifact_id: UUID, ctx: AuthContext
    ) -> List[Dict[str, Any]]:
        """List an artifact's revisions oldest-first.

        Returns the same entry shape the diff API already publishes for
        Diagram (``version``/``label``/``modified_at``/``content_available``),
        so ``ArtifactDiffService`` can serve one format for every type.
        """
        self._set_tenant_context(ctx)
        rows = ArtifactVersion.objects.filter(artifact_id=artifact_id).order_by(
            "revision"
        )
        return [
            {
                "version": row.revision,
                "label": f"v{row.revision}",
                "modified_at": row.created_at.isoformat() if row.created_at else None,
                # Every row is a stored snapshot — always retrievable.
                "content_available": True,
            }
            for row in rows
        ]

    def get_payload(
        self, artifact_id: UUID, revision: int, ctx: AuthContext
    ) -> Optional[Dict[str, Any]]:
        """Return the stored snapshot for *revision*, or ``None`` if absent."""
        self._set_tenant_context(ctx)
        row = ArtifactVersion.objects.filter(
            artifact_id=artifact_id, revision=revision
        ).first()
        return row.payload if row is not None else None


__all__ = [
    "ArtifactVersionService",
    "lineage_anchor_artifact_id",
    "snapshot_fields",
]
