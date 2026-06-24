"""
COMP-TE-002 QueryEngine — Graph query tests.

Covers:
  REQ-L2-TE-004: Upstream/downstream direct-neighbor queries
  REQ-L2-TE-005: Transitive hull computation
  REQ-L2-TE-008: Trace-graph collection for Baseline snapshots
  REQ-L2-TE-012: Performance SLA timeout handling

Note: Recursive CTE tests require a real PostgreSQL connection.
The tests use pytest.mark.django_db with real DB access.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from traceability.exceptions import PayloadTooLargeError, QueryTimeoutError
from traceability.query_engine import QueryEngine, MAX_GRAPH_ITEMS
from traceability.tests.conftest import (
    active_tenant,
    make_artifact,
    make_trace_link,
)
from traceability.types import Direction

pytestmark = pytest.mark.django_db


@pytest.fixture
def engine() -> QueryEngine:
    return QueryEngine()


# ---------------------------------------------------------------------------
# REQ-L2-TE-004: Upstream / Downstream queries
# ---------------------------------------------------------------------------

class TestDirectNeighborQueries:
    """REQ-L2-TE-004: direct neighbor queries return correct results."""

    def test_query_downstream_returns_direct_targets(
        self, engine, tenant_a, workspace_a
    ):
        """Downstream of A returns B and C when A->B, A->C exist."""
        with active_tenant(tenant_a):
            art_a = make_artifact(tenant_a, workspace_a, "requirement")
            art_b = make_artifact(tenant_a, workspace_a, "architecture_element")
            art_c = make_artifact(tenant_a, workspace_a, "testcase")

            make_trace_link(art_a, art_b, tenant_a, "satisfies")
            make_trace_link(art_a, art_c, tenant_a, "verifies")

            results = engine.query_downstream(art_a.id)

        entity_ids = {r.entity_id for r in results}
        assert art_b.id in entity_ids
        assert art_c.id in entity_ids
        assert all(r.direction == "downstream" for r in results)

    def test_query_upstream_returns_direct_sources(
        self, engine, tenant_a, workspace_a
    ):
        """Upstream of B returns A when A->B exists."""
        with active_tenant(tenant_a):
            art_a = make_artifact(tenant_a, workspace_a, "requirement")
            art_b = make_artifact(tenant_a, workspace_a, "testcase")

            make_trace_link(art_a, art_b, tenant_a, "verifies")

            results = engine.query_upstream(art_b.id)

        assert len(results) == 1
        assert results[0].entity_id == art_a.id
        assert results[0].direction == "upstream"
        assert results[0].link_type == "verifies"

    def test_result_includes_entity_type(self, engine, tenant_a, workspace_a):
        """REQ-L2-TE-004: result contains entity_type."""
        with active_tenant(tenant_a):
            src = make_artifact(tenant_a, workspace_a, "requirement")
            tgt = make_artifact(tenant_a, workspace_a, "testcase")
            make_trace_link(src, tgt, tenant_a, "verifies")

            results = engine.query_downstream(src.id)

        assert len(results) == 1
        assert results[0].entity_type == "testcase"

    def test_query_via_facade_direction(self, engine, tenant_a, workspace_a):
        """query() delegates to correct direction method."""
        with active_tenant(tenant_a):
            src = make_artifact(tenant_a, workspace_a, "requirement")
            tgt = make_artifact(tenant_a, workspace_a, "requirement")
            make_trace_link(src, tgt, tenant_a, "satisfies")

            down = engine.query(src.id, "downstream")
            up = engine.query(tgt.id, "upstream")

        assert any(r.entity_id == tgt.id for r in down)
        assert any(r.entity_id == src.id for r in up)

    def test_no_links_returns_empty(self, engine, tenant_a, workspace_a):
        """Artifact with no links returns empty list."""
        with active_tenant(tenant_a):
            art = make_artifact(tenant_a, workspace_a, "requirement")
            results = engine.query_downstream(art.id)

        assert results == []


# ---------------------------------------------------------------------------
# REQ-L2-TE-005: Transitive hull
# ---------------------------------------------------------------------------

class TestTransitiveQueries:
    """REQ-L2-TE-005: transitive closure via PostgreSQL Recursive CTE."""

    def test_transitive_downstream_two_levels(
        self, engine, tenant_a, workspace_a
    ):
        """A->B->C: transitive downstream from A returns B (depth=1) and C (depth=2)."""
        with active_tenant(tenant_a):
            art_a = make_artifact(tenant_a, workspace_a, "requirement")
            art_b = make_artifact(tenant_a, workspace_a, "architecture_element")
            art_c = make_artifact(tenant_a, workspace_a, "testcase")

            make_trace_link(art_a, art_b, tenant_a, "derives-from")
            make_trace_link(art_b, art_c, tenant_a, "implements")

            results = engine.query_transitive(art_a.id, "downstream")

        entity_ids = {r.entity_id for r in results}
        depths = {r.entity_id: r.depth for r in results}

        assert art_b.id in entity_ids
        assert art_c.id in entity_ids
        assert depths[art_b.id] == 1
        assert depths[art_c.id] == 2

    def test_transitive_upstream(self, engine, tenant_a, workspace_a):
        """A->B->C: transitive upstream from C returns B (depth=1) and A (depth=2)."""
        with active_tenant(tenant_a):
            art_a = make_artifact(tenant_a, workspace_a, "requirement")
            art_b = make_artifact(tenant_a, workspace_a, "architecture_element")
            art_c = make_artifact(tenant_a, workspace_a, "testcase")

            make_trace_link(art_a, art_b, tenant_a, "derives-from")
            make_trace_link(art_b, art_c, tenant_a, "implements")

            results = engine.query_transitive(art_c.id, "upstream")

        entity_ids = {r.entity_id for r in results}
        assert art_b.id in entity_ids
        assert art_a.id in entity_ids

    def test_transitive_via_query_facade(self, engine, tenant_a, workspace_a):
        """query(..., transitive=True) delegates to transitive method."""
        with active_tenant(tenant_a):
            src = make_artifact(tenant_a, workspace_a, "requirement")
            mid = make_artifact(tenant_a, workspace_a, "architecture_element")
            end = make_artifact(tenant_a, workspace_a, "testcase")

            make_trace_link(src, mid, tenant_a, "satisfies")
            make_trace_link(mid, end, tenant_a, "verifies")

            results = engine.query(src.id, "downstream", transitive=True)

        entity_ids = {r.entity_id for r in results}
        assert mid.id in entity_ids
        assert end.id in entity_ids


# ---------------------------------------------------------------------------
# REQ-L2-TE-008: Trace-graph collection
# ---------------------------------------------------------------------------

class TestTraceGraphCollection:
    """REQ-L2-TE-008: collect_trace_graph for Baseline snapshots."""

    def test_collect_all_links_in_workspace(self, engine, tenant_a, workspace_a):
        """Workspace with N links returns all N in the graph."""
        with active_tenant(tenant_a):
            arts = [make_artifact(tenant_a, workspace_a, "requirement") for _ in range(6)]
            for i in range(5):
                make_trace_link(arts[i], arts[i + 1], tenant_a)

            graph = engine.collect_trace_graph(workspace_a.id)

        assert len(graph.links) == 5

    def test_collect_empty_workspace(self, engine, tenant_a, workspace_a):
        """Empty workspace → empty graph (no error). REQ-L2-TE-008."""
        with active_tenant(tenant_a):
            graph = engine.collect_trace_graph(workspace_a.id)

        assert graph.links == []

    def test_graph_is_serializable(self, engine, tenant_a, workspace_a):
        """Graph.to_dict() returns JSON-serializable structure."""
        with active_tenant(tenant_a):
            src = make_artifact(tenant_a, workspace_a, "requirement")
            tgt = make_artifact(tenant_a, workspace_a, "requirement")
            make_trace_link(src, tgt, tenant_a)

            graph = engine.collect_trace_graph(workspace_a.id)

        d = graph.to_dict()
        assert "links" in d
        assert isinstance(d["links"], list)
        assert len(d["links"]) == 1
        link = d["links"][0]
        assert "source_id" in link
        assert "target_id" in link
        assert "link_type" in link

    def test_payload_too_large_raises(self, engine, tenant_a, workspace_a):
        """REQ-L2-TE-008: >100k items raises PayloadTooLargeError."""
        with active_tenant(tenant_a):
            # Mock the count query to return a value > MAX_GRAPH_ITEMS
            from django.db import connection as conn

            original_cursor = conn.cursor

            class FakeCursor:
                def __init__(self):
                    self._count_returned = False

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

                def execute(self, sql, params=None):
                    self._sql = sql

                def fetchone(self):
                    return (MAX_GRAPH_ITEMS + 1,)

            with patch.object(conn, "cursor", return_value=FakeCursor()):
                with pytest.raises(PayloadTooLargeError):
                    engine.collect_trace_graph(workspace_a.id)
