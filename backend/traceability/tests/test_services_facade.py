"""
ARCH-L1-007 TraceabilityEngine — services.py facade integration tests.

Validates that the public service API contracts are intact and correctly
delegate to the underlying components.

Covers:
  IF-TE-EXT-IN-001: query()
  IF-TE-EXT-IN-002: coverage()
  IF-TE-EXT-IN-003: TraceLink CRUD via services
  IF-TE-EXT-IN-004: collect_trace_graph()
  REQ-L2-TE-001, REQ-L2-TE-004, REQ-L2-TE-006, REQ-L2-TE-008
"""
from __future__ import annotations

import uuid

import pytest

import traceability.services as svc
from traceability.exceptions import (
    CycleDetectedError,
    InvalidLinkTypeError,
)
from traceability.tests.conftest import (
    active_tenant,
    make_artifact,
    make_requirement,
    make_test_case,
    make_trace_link,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# TraceLink CRUD via facade (IF-TE-EXT-IN-003)
# ---------------------------------------------------------------------------

class TestFacadeCRUD:
    """TraceLink CRUD via the public services module."""

    def test_create_and_get_via_facade(self, tenant_a, workspace_a):
        """create_trace_link + get_trace_link round-trip."""
        with active_tenant(tenant_a):
            src = make_artifact(tenant_a, workspace_a, "requirement")
            tgt = make_artifact(tenant_a, workspace_a, "requirement")

            link = svc.create_trace_link(src.id, tgt.id, "satisfies")
            retrieved = svc.get_trace_link(link.id)

        assert retrieved.id == link.id
        assert retrieved.link_type == "satisfies"

    def test_update_via_facade(self, tenant_a, workspace_a):
        """update_trace_link changes link_type."""
        with active_tenant(tenant_a):
            src = make_artifact(tenant_a, workspace_a, "requirement")
            tgt = make_artifact(tenant_a, workspace_a, "requirement")
            link = svc.create_trace_link(src.id, tgt.id, "satisfies")
            updated = svc.update_trace_link(link.id, link_type="implements")

        assert updated.link_type == "implements"

    def test_delete_via_facade(self, tenant_a, workspace_a):
        """delete_trace_link removes the link."""
        from persistence.models import TraceLink
        with active_tenant(tenant_a):
            src = make_artifact(tenant_a, workspace_a, "requirement")
            tgt = make_artifact(tenant_a, workspace_a, "requirement")
            link = svc.create_trace_link(src.id, tgt.id, "satisfies")
            svc.delete_trace_link(link.id)

            with pytest.raises(TraceLink.DoesNotExist):
                svc.get_trace_link(link.id)

    def test_batch_create_via_facade(self, tenant_a, workspace_a):
        """batch_create_trace_links creates all items atomically."""
        with active_tenant(tenant_a):
            arts = [make_artifact(tenant_a, workspace_a, "requirement") for _ in range(4)]
            items = [
                {"source_id": arts[i].id, "target_id": arts[i + 1].id, "link_type": "satisfies"}
                for i in range(3)
            ]
            created = svc.batch_create_trace_links(items)

        assert len(created) == 3

    def test_invalid_link_type_via_facade(self, tenant_a, workspace_a):
        """create_trace_link with bad type raises InvalidLinkTypeError."""
        with active_tenant(tenant_a):
            src = make_artifact(tenant_a, workspace_a, "requirement")
            tgt = make_artifact(tenant_a, workspace_a, "requirement")

            with pytest.raises(InvalidLinkTypeError):
                svc.create_trace_link(src.id, tgt.id, "bad-type")


# ---------------------------------------------------------------------------
# Query facade (IF-TE-EXT-IN-001)
# ---------------------------------------------------------------------------

class TestFacadeQuery:
    """query() facade delegates to QueryEngine correctly."""

    def test_query_downstream_via_facade(self, tenant_a, workspace_a):
        """query(direction='downstream') returns downstream neighbors."""
        with active_tenant(tenant_a):
            src = make_artifact(tenant_a, workspace_a, "requirement")
            tgt = make_artifact(tenant_a, workspace_a, "requirement")
            make_trace_link(src, tgt, tenant_a, "satisfies")

            results = svc.query(src.id, "downstream")

        assert any(r.entity_id == tgt.id for r in results)

    def test_query_upstream_via_facade(self, tenant_a, workspace_a):
        """query(direction='upstream') returns upstream neighbors."""
        with active_tenant(tenant_a):
            src = make_artifact(tenant_a, workspace_a, "requirement")
            tgt = make_artifact(tenant_a, workspace_a, "requirement")
            make_trace_link(src, tgt, tenant_a, "satisfies")

            results = svc.query(tgt.id, "upstream")

        assert any(r.entity_id == src.id for r in results)


# ---------------------------------------------------------------------------
# Coverage facade (IF-TE-EXT-IN-002)
# ---------------------------------------------------------------------------

class TestFacadeCoverage:
    """coverage() facade delegates to CoverageCalculator."""

    def test_coverage_via_facade(self, tenant_a, workspace_a):
        """coverage() returns a CoverageReport."""
        with active_tenant(tenant_a):
            art_req, _ = make_requirement(tenant_a, workspace_a, "R-1")
            tc_art, _ = make_test_case(tenant_a, workspace_a, "TC-1")
            make_trace_link(art_req, tc_art, tenant_a, "verifies")

            report = svc.coverage(workspace_a.id)

        assert report.total == 1
        assert report.covered == 1
        assert report.percentage == 100.0


# ---------------------------------------------------------------------------
# collect_trace_graph facade (IF-TE-EXT-IN-004)
# ---------------------------------------------------------------------------

class TestFacadeCollectTraceGraph:
    """collect_trace_graph() facade delegates to QueryEngine."""

    def test_collect_trace_graph_via_facade(self, tenant_a, workspace_a):
        """collect_trace_graph() returns a TraceGraphData."""
        with active_tenant(tenant_a):
            src = make_artifact(tenant_a, workspace_a, "requirement")
            tgt = make_artifact(tenant_a, workspace_a, "requirement")
            make_trace_link(src, tgt, tenant_a)

            graph = svc.collect_trace_graph(workspace_a.id)

        assert len(graph.links) == 1

    def test_graph_integrity_via_facade(self, tenant_a, workspace_a):
        """validate_graph_integrity() returns valid=True for acyclic graph."""
        with active_tenant(tenant_a):
            src = make_artifact(tenant_a, workspace_a, "requirement")
            tgt = make_artifact(tenant_a, workspace_a, "requirement")
            make_trace_link(src, tgt, tenant_a)

            result = svc.validate_graph_integrity()

        assert result["valid"] is True


# ---------------------------------------------------------------------------
# VCRM facade
# ---------------------------------------------------------------------------

class TestFacadeVCRM:
    """VCRM export via public services."""

    def test_export_csv_via_facade(self, tenant_a, workspace_a):
        """export_vcrm_csv returns a non-empty string for non-empty workspace."""
        with active_tenant(tenant_a):
            make_requirement(tenant_a, workspace_a, "R-1")
            csv_str = svc.export_vcrm_csv(workspace_a.id)

        assert isinstance(csv_str, str)
        assert "requirement_id" in csv_str

    def test_export_pdf_raises_via_facade(self, tenant_a, workspace_a):
        """export_vcrm_pdf raises NotImplementedError."""
        with active_tenant(tenant_a):
            with pytest.raises(NotImplementedError):
                svc.export_vcrm_pdf(workspace_a.id)
