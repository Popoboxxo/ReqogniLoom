"""Full rebuild path for the Workspace Context Graph (Issue #377, Task 8).

Why this exists: the outbox is not a retention log — re-enabling a
previously-disabled workspace cannot "catch up" by replaying old events
(published rows aren't guaranteed retained). Enabling context_graph for a
workspace must trigger a full rebuild from CURRENT state, not from the event
stream. This is the mechanism Task 9's settings toggle calls on a
``False -> True`` transition, and the management command below exposes it
directly for operators.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List
from uuid import UUID

from django.utils import timezone

from persistence.middleware import clear_request_tenant, set_request_tenant

logger = logging.getLogger(__name__)


@dataclass
class RebuildResult:
    workspace_id: UUID
    node_count: int = 0
    edge_count: int = 0
    artifacts_processed: int = 0
    artifact_errors: int = 0
    error: str = ""


def rebuild_workspace_graph(workspace_id: UUID) -> RebuildResult:
    """Iterate every Artifact in *workspace_id* and re-run every enabled
    generator for each, upserting via the SAME mechanism the projector uses
    (:meth:`context_graph.projector.ContextGraphProjector._reproject_artifact`
    — reused, not duplicated, per the plan).

    Does NOT create a WorkspaceContextSettings row if one does not exist —
    "missing row = feature off" is a read-path AND an admin-path rule; only
    the settings-write path (Task 9) creates rows.
    """
    from context_graph.models import WorkspaceContextSettings
    from context_graph.projector import ContextGraphProjector
    from persistence.models import Artifact, Workspace

    tenant_id = (
        Workspace.unscoped.filter(id=workspace_id).values_list("tenant_id", flat=True).first()
    )
    if tenant_id is None:
        return RebuildResult(workspace_id=workspace_id, error=f"Workspace {workspace_id} not found")

    set_request_tenant(tenant_id)
    try:
        settings_row = WorkspaceContextSettings.objects.filter(workspace_id=workspace_id).first()
        if settings_row is None:
            return RebuildResult(
                workspace_id=workspace_id,
                error=(
                    "No WorkspaceContextSettings row for this workspace — "
                    "enable the feature first (creates the row, Task 9)."
                ),
            )

        enabled_generators: List[str] = settings_row.enabled_generators or []
        artifact_ids = list(
            Artifact.objects.filter(workspace_id=workspace_id).values_list("id", flat=True)
        )

        processed = 0
        errors = 0
        for artifact_id in artifact_ids:
            try:
                ContextGraphProjector._reproject_artifact(artifact_id, enabled_generators)
                processed += 1
            except Exception:  # noqa: BLE001 — one bad artifact must not abort the rebuild
                errors += 1
                logger.exception(
                    "rebuild_workspace_graph: artifact %s failed for workspace %s",
                    artifact_id,
                    workspace_id,
                )

        from context_graph.models import ContextEdge

        edge_count = ContextEdge.objects.filter(source__workspace_id=workspace_id).count()

        settings_row.node_count = len(artifact_ids)
        settings_row.edge_count = edge_count
        settings_row.last_projected_at = timezone.now()
        settings_row.last_refresh_at = timezone.now()
        settings_row.last_error = (
            f"{errors} artifact(s) failed during rebuild" if errors else ""
        )
        settings_row.save(
            update_fields=[
                "node_count",
                "edge_count",
                "last_projected_at",
                "last_refresh_at",
                "last_error",
            ]
        )

        return RebuildResult(
            workspace_id=workspace_id,
            node_count=len(artifact_ids),
            edge_count=edge_count,
            artifacts_processed=processed,
            artifact_errors=errors,
        )
    finally:
        clear_request_tenant()


__all__ = ["rebuild_workspace_graph", "RebuildResult"]
