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


__all__ = ["ArtifactVersionService"]
