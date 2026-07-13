"""
COMP-TE-002 QueryEngine — Graph traversal queries on TraceLink data.

leaf_id: COMP-TE-002_QueryEngine
req_id: REQ-L2-TE-004, REQ-L2-TE-005, REQ-L2-TE-008, REQ-L2-TE-012,
        REQ-L2-TE-015

Responsibilities:
- Upstream/downstream queries on direct neighbors (REQ-L2-TE-004)
- Transitive closure via PostgreSQL Recursive CTE (REQ-L2-TE-005)
- Trace-graph collection for Baseline snapshots (REQ-L2-TE-008)
- Cross-project graph traversal with workspace annotation (REQ-L2-TE-015)
- Performance SLA enforcement: ≤200ms for graph queries (REQ-L2-TE-012)

Interface contracts consumed:
- IF-TE-INT-001: TraceLinkManager.get_trace_links()
- IF-TE-EXT-OUT-001: Django ORM (raw SQL for Recursive CTE)

Interface contracts exposed:
- IF-TE-EXT-IN-001: query(artifact_id, direction, ctx)
- IF-TE-EXT-IN-004: collect_trace_graph(workspace_id, ctx)
- IF-TE-INT-005: to VCRMReportGenerator

Architecture:
  docs/se/L1/Gesamtsystem/L2/TraceabilityEngineSystem/Components/
  COMP-TE-002_QueryEngine/L3_COMP-TE-002_QueryEngine_Architecture.md
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Optional

from django.db import connection, OperationalError, ProgrammingError

from persistence.tenancy import TenantContext

from traceability.exceptions import PayloadTooLargeError, QueryTimeoutError
from traceability.types import (
    Direction,
    NeighborResult,
    TraceGraphData,
    TransitiveResult,
)

logger = logging.getLogger(__name__)

# Performance SLA constants (REQ-L2-TE-012)
GRAPH_QUERY_SLA_MS = 200
GRAPH_QUERY_TIMEOUT_S = 5
GRAPH_COLLECTION_SLA_MS = 500
MAX_GRAPH_ITEMS = 100_000  # REQ-L2-TE-008 memory protection


class QueryEngine:
    """COMP-TE-002: Graph traversal queries on the TraceLink graph.

    Uses PostgreSQL Recursive CTEs for transitive queries (ADR-TE-02).
    All queries are tenant-scoped via TenantContext.

    REQ-L2-TE-004 / REQ-L2-TE-005 / REQ-L2-TE-008 / REQ-L2-TE-012
    """

    # IF-TE-EXT-IN-001
    def query(
        self,
        artifact_id: uuid.UUID,
        direction: str,
        transitive: bool = False,
        cross_project: bool = False,
    ) -> list[NeighborResult | TransitiveResult]:
        """Entry-point for upstream/downstream queries.

        REQ-L2-TE-004 (direct neighbors) and REQ-L2-TE-005 (transitive).

        Args:
            artifact_id: The starting artifact.
            direction: "upstream" | "downstream".
            transitive: If True, returns all reachable nodes (transitive hull).
            cross_project: If True, traverses across workspace boundaries.

        Returns:
            List of NeighborResult (transitive=False) or TransitiveResult.

        Raises:
            QueryTimeoutError: if the DB statement timeout fires.
        """
        if direction == Direction.UPSTREAM or direction == "upstream":
            if transitive:
                return self.query_transitive(
                    artifact_id, "upstream", cross_project=cross_project
                )
            return self.query_upstream(artifact_id, cross_project=cross_project)
        else:
            if transitive:
                return self.query_transitive(
                    artifact_id, "downstream", cross_project=cross_project
                )
            return self.query_downstream(artifact_id, cross_project=cross_project)

    def query_upstream(
        self,
        artifact_id: uuid.UUID,
        cross_project: bool = False,
    ) -> list[NeighborResult]:
        """Return all direct upstream neighbors (target = artifact_id).

        REQ-L2-TE-004: ≤200ms p95. Link direction: source→target means
        source is "upstream" of target.
        """
        t0 = time.monotonic()
        tenant_id = TenantContext.get_tenant()

        sql = """
            SELECT
                tl.id,
                tl.source_id  AS entity_id,
                a.artifact_type AS entity_type,
                tl.link_type,
                a.workspace_id
            FROM pl_tracelink tl
            JOIN pl_artifact a ON a.id = tl.source_id
            WHERE tl.target_id = %s
              AND tl.tenant_id = %s
        """
        params = [str(artifact_id), str(tenant_id)]

        rows = self._execute_with_timeout(sql, params)
        results = [
            NeighborResult(
                entity_id=uuid.UUID(str(row[1])),
                entity_type=row[2],
                link_type=row[3],
                direction="upstream",
                workspace_id=uuid.UUID(str(row[4])) if row[4] else None,
            )
            for row in rows
        ]
        self._log_sla("query_upstream", t0, GRAPH_QUERY_SLA_MS)
        return results

    def query_downstream(
        self,
        artifact_id: uuid.UUID,
        cross_project: bool = False,
    ) -> list[NeighborResult]:
        """Return all direct downstream neighbors (source = artifact_id).

        REQ-L2-TE-004: ≤200ms p95.
        """
        t0 = time.monotonic()
        tenant_id = TenantContext.get_tenant()

        sql = """
            SELECT
                tl.id,
                tl.target_id  AS entity_id,
                a.artifact_type AS entity_type,
                tl.link_type,
                a.workspace_id
            FROM pl_tracelink tl
            JOIN pl_artifact a ON a.id = tl.target_id
            WHERE tl.source_id = %s
              AND tl.tenant_id = %s
        """
        params = [str(artifact_id), str(tenant_id)]

        rows = self._execute_with_timeout(sql, params)
        results = [
            NeighborResult(
                entity_id=uuid.UUID(str(row[1])),
                entity_type=row[2],
                link_type=row[3],
                direction="downstream",
                workspace_id=uuid.UUID(str(row[4])) if row[4] else None,
            )
            for row in rows
        ]
        self._log_sla("query_downstream", t0, GRAPH_QUERY_SLA_MS)
        return results

    def query_transitive(
        self,
        artifact_id: uuid.UUID,
        direction: str,
        cross_project: bool = False,
    ) -> list[TransitiveResult]:
        """Return all transitively reachable nodes via Recursive CTE.

        REQ-L2-TE-005: PostgreSQL WITH RECURSIVE, ≤200ms p95.

        The CTE follows directed edges; direction determines which FK to
        traverse (source→target for downstream, target→source for upstream).
        A CYCLE detection clause prevents infinite loops on unexpected cycles.
        """
        t0 = time.monotonic()
        tenant_id = TenantContext.get_tenant()

        if direction == "downstream":
            # downstream: follow source → target edges
            sql = """
                WITH RECURSIVE traversal AS (
                    SELECT
                        tl.target_id AS entity_id,
                        a.artifact_type AS entity_type,
                        tl.link_type,
                        a.workspace_id,
                        1 AS depth,
                        ARRAY[tl.source_id] AS visited
                    FROM pl_tracelink tl
                    JOIN pl_artifact a ON a.id = tl.target_id
                    WHERE tl.source_id = %s
                      AND tl.tenant_id = %s

                    UNION ALL

                    SELECT
                        tl.target_id,
                        a.artifact_type,
                        tl.link_type,
                        a.workspace_id,
                        tr.depth + 1,
                        tr.visited || tl.source_id
                    FROM pl_tracelink tl
                    JOIN pl_artifact a ON a.id = tl.target_id
                    JOIN traversal tr ON tr.entity_id = tl.source_id
                    WHERE tl.tenant_id = %s
                      AND NOT (tl.target_id = ANY(tr.visited))
                )
                SELECT entity_id, entity_type, link_type, workspace_id, depth
                FROM traversal
            """
            params = [str(artifact_id), str(tenant_id), str(tenant_id)]
            dir_label = "downstream"
        else:
            # upstream: follow target → source edges
            sql = """
                WITH RECURSIVE traversal AS (
                    SELECT
                        tl.source_id AS entity_id,
                        a.artifact_type AS entity_type,
                        tl.link_type,
                        a.workspace_id,
                        1 AS depth,
                        ARRAY[tl.target_id] AS visited
                    FROM pl_tracelink tl
                    JOIN pl_artifact a ON a.id = tl.source_id
                    WHERE tl.target_id = %s
                      AND tl.tenant_id = %s

                    UNION ALL

                    SELECT
                        tl.source_id,
                        a.artifact_type,
                        tl.link_type,
                        a.workspace_id,
                        tr.depth + 1,
                        tr.visited || tl.target_id
                    FROM pl_tracelink tl
                    JOIN pl_artifact a ON a.id = tl.source_id
                    JOIN traversal tr ON tr.entity_id = tl.target_id
                    WHERE tl.tenant_id = %s
                      AND NOT (tl.source_id = ANY(tr.visited))
                )
                SELECT entity_id, entity_type, link_type, workspace_id, depth
                FROM traversal
            """
            params = [str(artifact_id), str(tenant_id), str(tenant_id)]
            dir_label = "upstream"

        rows = self._execute_with_timeout(sql, params)
        results = [
            TransitiveResult(
                entity_id=uuid.UUID(str(row[0])),
                entity_type=row[1],
                link_type=row[2],
                direction=dir_label,
                depth=row[4],
                workspace_id=uuid.UUID(str(row[3])) if row[3] else None,
            )
            for row in rows
        ]
        self._log_sla("query_transitive", t0, GRAPH_QUERY_SLA_MS)
        return results

    # IF-TE-EXT-IN-004
    def collect_trace_graph(
        self,
        workspace_id: uuid.UUID,
    ) -> TraceGraphData:
        """Collect all TraceLinks of a workspace for Baseline snapshots.

        REQ-L2-TE-008: ≤500ms, memory-limit protection at 100k items.
        """
        t0 = time.monotonic()
        tenant_id = TenantContext.get_tenant()

        # Count first to guard memory limit (REQ-L2-TE-008)
        count_sql = """
            SELECT COUNT(*)
            FROM pl_tracelink tl
            JOIN pl_artifact a ON a.id = tl.source_id
            WHERE a.workspace_id = %s
              AND tl.tenant_id = %s
        """
        with connection.cursor() as cur:
            cur.execute(count_sql, [str(workspace_id), str(tenant_id)])
            count = cur.fetchone()[0]

        if count > MAX_GRAPH_ITEMS:
            raise PayloadTooLargeError()

        sql = """
            SELECT
                tl.id,
                tl.source_id,
                tl.target_id,
                tl.link_type,
                tl.tenant_id
            FROM pl_tracelink tl
            JOIN pl_artifact a ON a.id = tl.source_id
            WHERE a.workspace_id = %s
              AND tl.tenant_id = %s
            ORDER BY tl.id
        """
        with connection.cursor() as cur:
            cur.execute(sql, [str(workspace_id), str(tenant_id)])
            rows = cur.fetchall()

        links = [
            {
                "id": str(row[0]),
                "source_id": str(row[1]),
                "target_id": str(row[2]),
                "link_type": row[3],
                "tenant_id": str(row[4]),
            }
            for row in rows
        ]
        self._log_sla("collect_trace_graph", t0, GRAPH_COLLECTION_SLA_MS)
        return TraceGraphData(links=links)

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _execute_with_timeout(
        self,
        sql: str,
        params: list[Any],
        timeout_ms: int = GRAPH_QUERY_TIMEOUT_S * 1000,
    ) -> list[tuple]:
        """Execute a raw query with a PostgreSQL statement timeout.

        REQ-L2-TE-012: harter DB-Timeout fuer alle Queries.
        Raises QueryTimeoutError if the DB statement timeout fires.
        """
        try:
            with connection.cursor() as cur:
                cur.execute(
                    "SET LOCAL statement_timeout = %s", [timeout_ms]
                )
                cur.execute(sql, params)
                return cur.fetchall()
        except (OperationalError, ProgrammingError) as exc:
            msg = str(exc).lower()
            if "statement timeout" in msg or "canceling statement" in msg:
                raise QueryTimeoutError() from exc
            raise

    @staticmethod
    def _log_sla(label: str, t0: float, sla_ms: int) -> None:
        """Log a warning if the query exceeded the SLA (ADR-L3-TE2-03)."""
        elapsed_ms = (time.monotonic() - t0) * 1000
        if elapsed_ms > sla_ms:
            logger.warning(
                "QueryEngine SLA breach: %s took %.1fms (SLA: %dms)",
                label,
                elapsed_ms,
                sla_ms,
            )


__all__ = ["QueryEngine"]
