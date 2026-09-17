"""Shared types for the Workspace Context Graph (Issue #377, v1 slice).

Kept in their own module (not in ``projector.py`` or a ``generators/*``
module) so generators and the projector can both import the candidate shape
without an import cycle.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict
from uuid import UUID


@dataclass(frozen=True)
class ContextEdgeCandidate:
    """A single candidate edge a generator believes should exist right now.

    The projector upserts these against ``ContextEdge``'s
    ``(source, target, edge_kind, origin)`` unique constraint and deletes any
    existing row with the same ``origin`` for the artifact that the
    generator's fresh run did NOT return (stale-edge cleanup) — see
    :mod:`context_graph.projector`.
    """

    source_id: UUID
    target_id: UUID
    edge_kind: str
    origin: str
    confidence: float
    generator: str
    evidence: Dict[str, Any] = field(default_factory=dict)


__all__ = ["ContextEdgeCandidate"]
