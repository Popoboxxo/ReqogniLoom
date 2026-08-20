"""Celery tasks for the Workspace Context Graph (Issue #377, Task 9).

Falls through to the 'default' queue (reqogniloom/celery.py) — not 'events'
(that queue is reserved for the latency-sensitive outbox dispatch the
projector itself runs on) and not 'llm' (this task makes no LLM call, the v1
generator is deterministic). Matches the 'default' queue's own description:
"everything else (resilience/audit maintenance tasks)".
"""
from __future__ import annotations

import logging
from uuid import UUID

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="context_graph.rebuild_workspace_graph")
def rebuild_workspace_graph_task(workspace_id: str) -> dict:
    """Async wrapper around :func:`context_graph.admin_ops.rebuild_workspace_graph`.

    Triggered by the settings-write path (Task 9) on a False -> True
    ``enabled`` transition — "do not run a potentially-large rebuild
    synchronously in the request/response cycle" (Task 9 spec).
    """
    from context_graph.admin_ops import rebuild_workspace_graph

    result = rebuild_workspace_graph(UUID(str(workspace_id)))
    if result.error:
        logger.error(
            "rebuild_workspace_graph_task: workspace=%s failed: %s",
            workspace_id,
            result.error,
        )
    else:
        logger.info(
            "rebuild_workspace_graph_task: workspace=%s processed=%d edges=%d errors=%d",
            workspace_id,
            result.artifacts_processed,
            result.edge_count,
            result.artifact_errors,
        )
    return {
        "workspace_id": str(workspace_id),
        "node_count": result.node_count,
        "edge_count": result.edge_count,
        "artifacts_processed": result.artifacts_processed,
        "artifact_errors": result.artifact_errors,
        "error": result.error,
    }


__all__ = ["rebuild_workspace_graph_task"]
