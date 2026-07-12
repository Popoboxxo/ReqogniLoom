"""
ARCH-L1-007 TraceabilityEngine — Read-model service (recursive CTE queries).

leaf_id: COMP-TE-002_QueryEngine (read-model extension)
req_id:  REQ-L2-TE-019

This module provides higher-level *read-model* graph queries built directly on
PostgreSQL recursive CTEs (Postgres 14+). It complements ``query_engine.py``
(neighbor / transitive-hull queries) with:

- ``impact_analysis`` — reachability with per-node path + depth tracking and a
  cycle guard, enriched with domain title/uid via a single batched query.
- ``find_path``       — shortest path(s) between two artifacts (BFS-style CTE).
- ``detect_cycles``   — enumerate cycles in a workspace's trace graph.

All queries are tenant-scoped: ``tenant_id`` is applied inside every CTE so no
row from another tenant can ever leak (multi-tenancy, REQ-L2-TE-011).

Performance:
- ``max_depth`` is hard-capped by the caller (REST layer) at 20 to prevent
  runaway recursion; this module additionally clamps it defensively.
- Enrichment fetches Artifact + domain-entity rows with ``artifact_id__in``
  batches — never per node (no N+1).

Public import surface:
    from traceability.service import (
        ImpactNode, TracePath,
        impact_analysis, find_path, detect_cycles,
    )
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

from django.db import connection

from traceability.types import VALID_LINK_TYPES

# Defensive hard cap (the REST layer also enforces this — REQ-L2-TE-019).
MAX_DEPTH_CAP = 20
DEFAULT_MAX_DEPTH = 10
DEFAULT_LIMIT = 200
MAX_LIMIT = 1000


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ImpactNode:
    """A single artifact reachable from the impact-analysis start node."""

    artifact_id: str
    artifact_type: str          # from Artifact.artifact_type
    title: str                  # from the backing domain entity
    uid: Optional[str]          # from the backing domain entity (may be None)
    link_type: str              # the link type that led to this node
    depth: int                  # hops from the start node (>= 1)
    path: list[str] = field(default_factory=list)  # artifact_ids start -> node

    def to_dict(self) -> dict:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "title": self.title,
            "uid": self.uid,
            "link_type": self.link_type,
            "depth": self.depth,
            "path": self.path,
        }


@dataclass
class TracePath:
    """A single path between two artifacts (list of artifact_ids)."""

    nodes: list[str]
    length: int

    def to_dict(self) -> dict:
        return {"nodes": self.nodes, "length": self.length}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp_depth(max_depth: int) -> int:
    if max_depth is None or max_depth < 1:
        return DEFAULT_MAX_DEPTH
    return min(int(max_depth), MAX_DEPTH_CAP)


def _clamp_limit(limit: int) -> int:
    if limit is None or limit < 1:
        return DEFAULT_LIMIT
    return min(int(limit), MAX_LIMIT)


def _validate_link_types(link_types: Optional[list[str]]) -> Optional[list[str]]:
    """Return a cleaned link_types list, or None. Unknown values are dropped."""
    if not link_types:
        return None
    cleaned = [lt for lt in link_types if lt in VALID_LINK_TYPES]
    return cleaned or None


def _enrich(artifact_ids: list[str], tenant_id: uuid.UUID) -> dict[str, dict]:
    """Batch-fetch artifact_type + title/uid for a set of artifact ids.

    Runs at most six queries total (Artifact + 4 persistence domain tables +
    1 application-layer ADR), independent of the number of nodes — avoids N+1
    (REQ-L2-TE-019, REQ-002).
    """
    from persistence.models import (
        ArchitectureElement,
        Artifact,
        Requirement,
        StakeholderNeed,
        TestCase,
    )

    if not artifact_ids:
        return {}

    info: dict[str, dict] = {}
    for art in Artifact.objects.filter(id__in=artifact_ids).values(
        "id", "artifact_type"
    ):
        info[str(art["id"])] = {
            "artifact_type": art["artifact_type"],
            "title": "",
            "uid": None,
        }

    # Domain entities carry the human-readable title + uid. Each is OneToOne on
    # Artifact, so a single artifact_id__in scan per table fully enriches.
    domain_models = (
        Requirement,
        ArchitectureElement,
        StakeholderNeed,
        TestCase,
    )
    for model in domain_models:
        for row in model.objects.filter(artifact_id__in=artifact_ids).values(
            "artifact_id", "title", "uid"
        ):
            key = str(row["artifact_id"])
            entry = info.get(key)
            if entry is not None:
                entry["title"] = row["title"] or ""
                entry["uid"] = row["uid"]

    # REQ-002: ADR lives in the application layer — enrich separately so that
    # impact-analysis nodes linked to ADRs also receive a human-readable title.
    try:
        from application.models import Adr

        for row in Adr.objects.filter(artifact_id__in=artifact_ids).values(
            "artifact_id", "title"
        ):
            key = str(row["artifact_id"])
            entry = info.get(key)
            if entry is not None:
                entry["title"] = row["title"] or ""
    except Exception:  # noqa: BLE001 — Adr model absent in some test configs
        pass

    return info


# ---------------------------------------------------------------------------
# 2a. Impact analysis
# ---------------------------------------------------------------------------

def impact_analysis(
    artifact_id: uuid.UUID,
    workspace_id: Optional[uuid.UUID],
    tenant_id: uuid.UUID,
    link_types: Optional[list[str]] = None,
    direction: str = "outgoing",
    max_depth: int = DEFAULT_MAX_DEPTH,
    limit: int = DEFAULT_LIMIT,
) -> list[ImpactNode]:
    """Return all artifacts reachable from *artifact_id* following TraceLinks.

    Uses a recursive CTE with an in-path cycle guard. Each returned node keeps
    the link_type that led to it, its depth, and the full artifact_id path.

    Args:
        artifact_id: Start artifact (Artifact.id).
        workspace_id: Unused for traversal (links are tenant-global) but kept
            for signature symmetry / future scoping.
        tenant_id: Active tenant — applied in every CTE branch.
        link_types: Optional whitelist of link_type values to traverse.
        direction: "outgoing" | "incoming" | "both".
        max_depth: Traversal depth cap (clamped to 20).
        limit: Max rows returned (clamped to 1000).

    Returns:
        List of ImpactNode, one per reachable artifact (shortest depth kept).
    """
    depth = _clamp_depth(max_depth)
    row_limit = _clamp_limit(limit)
    cleaned_types = _validate_link_types(link_types)

    direction = direction if direction in ("outgoing", "incoming", "both") else "outgoing"

    if direction == "outgoing":
        edge_sql = (
            "SELECT source_id AS frm, target_id AS to_, link_type "
            "FROM pl_tracelink WHERE tenant_id = %(tenant)s"
        )
    elif direction == "incoming":
        edge_sql = (
            "SELECT target_id AS frm, source_id AS to_, link_type "
            "FROM pl_tracelink WHERE tenant_id = %(tenant)s"
        )
    else:  # both — treat the graph as undirected
        edge_sql = (
            "SELECT source_id AS frm, target_id AS to_, link_type "
            "FROM pl_tracelink WHERE tenant_id = %(tenant)s "
            "UNION ALL "
            "SELECT target_id AS frm, source_id AS to_, link_type "
            "FROM pl_tracelink WHERE tenant_id = %(tenant)s"
        )

    params: dict = {
        "tenant": str(tenant_id),
        "start": str(artifact_id),
        "max_depth": depth,
        "limit": row_limit,
    }

    link_filter = ""
    if cleaned_types is not None:
        link_filter = "WHERE link_type = ANY(%(link_types)s)"
        params["link_types"] = cleaned_types

    sql = f"""
        WITH RECURSIVE all_edges AS ( {edge_sql} ),
        edges AS (
            SELECT frm, to_, link_type FROM all_edges {link_filter}
        ),
        impact(artifact_id, link_type, depth, path, cycle) AS (
            SELECT e.to_, e.link_type, 1,
                   ARRAY[e.frm, e.to_], (e.to_ = e.frm)
            FROM edges e
            WHERE e.frm = %(start)s
            UNION ALL
            SELECT e.to_, e.link_type, i.depth + 1,
                   i.path || e.to_, e.to_ = ANY(i.path)
            FROM edges e
            JOIN impact i ON e.frm = i.artifact_id
            WHERE NOT i.cycle AND i.depth < %(max_depth)s
        )
        SELECT artifact_id, link_type, depth, path
        FROM impact
        WHERE NOT cycle
        ORDER BY depth, artifact_id
        LIMIT %(limit)s
    """

    with connection.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    # Deduplicate to one node per artifact (keep shallowest depth — rows are
    # already ordered by depth ascending).
    seen: set[str] = set()
    ordered: list[tuple] = []
    node_ids: list[str] = []
    for art_id, link_type, node_depth, path in rows:
        key = str(art_id)
        if key in seen:
            continue
        seen.add(key)
        ordered.append((key, link_type, node_depth, [str(p) for p in path]))
        node_ids.append(key)

    enrichment = _enrich(node_ids, tenant_id)

    result: list[ImpactNode] = []
    for key, link_type, node_depth, path in ordered:
        meta = enrichment.get(key, {})
        result.append(
            ImpactNode(
                artifact_id=key,
                artifact_type=meta.get("artifact_type", ""),
                title=meta.get("title", ""),
                uid=meta.get("uid"),
                link_type=link_type,
                depth=node_depth,
                path=path,
            )
        )
    return result


# ---------------------------------------------------------------------------
# 2b. Path finding
# ---------------------------------------------------------------------------

def find_path(
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    workspace_id: Optional[uuid.UUID],
    tenant_id: uuid.UUID,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> Optional[list[TracePath]]:
    """Return the shortest path(s) from *source_id* to *target_id*.

    Follows directed outgoing edges (source -> target). Uses a BFS-style
    recursive CTE with an in-path cycle guard, then keeps only the paths of
    minimal length.

    Returns:
        A list of TracePath (all shortest paths), or None if unreachable.
    """
    depth = _clamp_depth(max_depth)

    sql = """
        WITH RECURSIVE search(node, path, depth, cycle) AS (
            SELECT tl.target_id,
                   ARRAY[tl.source_id, tl.target_id],
                   1,
                   (tl.target_id = tl.source_id)
            FROM pl_tracelink tl
            WHERE tl.source_id = %(source)s
              AND tl.tenant_id = %(tenant)s
            UNION ALL
            SELECT tl.target_id,
                   s.path || tl.target_id,
                   s.depth + 1,
                   tl.target_id = ANY(s.path)
            FROM pl_tracelink tl
            JOIN search s ON tl.source_id = s.node
            WHERE NOT s.cycle
              AND s.depth < %(max_depth)s
              AND tl.tenant_id = %(tenant)s
        )
        SELECT path, depth
        FROM search
        WHERE node = %(target)s
        ORDER BY depth
        LIMIT 100
    """
    params = {
        "source": str(source_id),
        "target": str(target_id),
        "tenant": str(tenant_id),
        "max_depth": depth,
    }

    with connection.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    if not rows:
        return None

    min_depth = min(r[1] for r in rows)
    paths: list[TracePath] = []
    seen: set[tuple] = set()
    for path, node_depth in rows:
        if node_depth != min_depth:
            continue
        nodes = tuple(str(p) for p in path)
        if nodes in seen:
            continue
        seen.add(nodes)
        paths.append(TracePath(nodes=list(nodes), length=len(nodes) - 1))
    return paths or None


# ---------------------------------------------------------------------------
# 2c. Cycle detection
# ---------------------------------------------------------------------------

def detect_cycles(
    workspace_id: uuid.UUID,
    tenant_id: uuid.UUID,
    limit: int = 100,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> list[list[str]]:
    """Return cycles found in the workspace's trace graph.

    A cycle is detected when a walk returns to its origin artifact. Each cycle
    is returned in a normalized minimal representation (rotated so the smallest
    artifact_id is first, without the repeated closing node), deduplicated.

    Uses a recursive CTE scoped to the workspace and tenant.
    """
    depth = _clamp_depth(max_depth)
    row_limit = _clamp_limit(limit)

    sql = """
        WITH RECURSIVE walk(origin, node, path, closed) AS (
            SELECT tl.source_id, tl.target_id,
                   ARRAY[tl.source_id, tl.target_id],
                   (tl.target_id = tl.source_id)
            FROM pl_tracelink tl
            JOIN pl_artifact a ON a.id = tl.source_id
            WHERE tl.tenant_id = %(tenant)s
              AND a.workspace_id = %(workspace)s
            UNION ALL
            SELECT w.origin, tl.target_id,
                   w.path || tl.target_id,
                   (tl.target_id = w.origin)
            FROM pl_tracelink tl
            JOIN walk w ON tl.source_id = w.node
            WHERE NOT w.closed
              AND array_length(w.path, 1) < %(max_depth)s
              AND tl.tenant_id = %(tenant)s
              AND NOT (tl.target_id = ANY(w.path) AND tl.target_id <> w.origin)
        )
        SELECT path
        FROM walk
        WHERE closed
        LIMIT %(limit)s
    """
    params = {
        "tenant": str(tenant_id),
        "workspace": str(workspace_id),
        "max_depth": depth,
        "limit": row_limit,
    }

    with connection.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    unique: dict[tuple, list[str]] = {}
    for (path,) in rows:
        nodes = [str(p) for p in path]
        # Drop the repeated closing node (path[-1] == path[0] == origin).
        if len(nodes) > 1 and nodes[0] == nodes[-1]:
            nodes = nodes[:-1]
        if len(nodes) < 2:
            continue
        # Normalize rotation: start at the smallest id for stable dedup.
        pivot = nodes.index(min(nodes))
        normalized = nodes[pivot:] + nodes[:pivot]
        unique[tuple(normalized)] = normalized

    return list(unique.values())


__all__ = [
    "ImpactNode",
    "TracePath",
    "impact_analysis",
    "find_path",
    "detect_cycles",
    "MAX_DEPTH_CAP",
    "DEFAULT_MAX_DEPTH",
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
]
