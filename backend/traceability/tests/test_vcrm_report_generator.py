"""
COMP-TE-004 VCRMReportGenerator — VCRM matrix generation and export tests.

Covers:
  REQ-L2-TE-013: VCRM matrix generation, CSV export, PDF optional
"""
from __future__ import annotations

import csv
import io

import pytest

from traceability.vcrm_report_generator import VCRMReportGenerator
from traceability.coverage_calculator import CoverageCalculator
from traceability.query_engine import QueryEngine
from traceability.tests.conftest import (
    active_tenant,
    make_artifact,
    make_requirement,
    make_test_case,
    make_trace_link,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def vcrm_gen() -> VCRMReportGenerator:
    return VCRMReportGenerator(
        coverage_calculator=CoverageCalculator(),
        query_engine=QueryEngine(),
    )


# ---------------------------------------------------------------------------
# REQ-L2-TE-013: VCRM matrix generation
# ---------------------------------------------------------------------------

class TestVCRMGeneration:
    """REQ-L2-TE-013: Matrix generation for workspace."""

    def test_empty_workspace_returns_empty_matrix(
        self, vcrm_gen, tenant_a, workspace_a
    ):
        """Empty workspace → empty matrix, no error."""
        with active_tenant(tenant_a):
            matrix = vcrm_gen.generate_vcrm(workspace_a.id)

        assert matrix.rows == []

    def test_requirement_without_test_case_gets_not_run(
        self, vcrm_gen, tenant_a, workspace_a
    ):
        """Requirement with no TestCase link → test_result = 'Not Run'."""
        with active_tenant(tenant_a):
            _, req = make_requirement(tenant_a, workspace_a, "R-1")
            matrix = vcrm_gen.generate_vcrm(workspace_a.id)

        assert len(matrix.rows) >= 1
        row = next(r for r in matrix.rows if r.requirement_id == str(req.id))
        assert row.test_result == "Not Run"

    def test_requirement_with_test_case_link_appears(
        self, vcrm_gen, tenant_a, workspace_a
    ):
        """Requirement linked to TestCase appears in the matrix."""
        with active_tenant(tenant_a):
            art_req, req = make_requirement(tenant_a, workspace_a, "R-1")
            tc_art, tc = make_test_case(tenant_a, workspace_a, "TC-1")
            make_trace_link(art_req, tc_art, tenant_a, "verifies")

            matrix = vcrm_gen.generate_vcrm(workspace_a.id)

        req_rows = [r for r in matrix.rows if r.requirement_id == str(req.id)]
        assert len(req_rows) >= 1
        tc_row = next(
            (r for r in req_rows if r.test_case_id == str(tc_art.id)), None
        )
        assert tc_row is not None

    def test_to_dict_returns_serializable_structure(
        self, vcrm_gen, tenant_a, workspace_a
    ):
        """VCRMMatrix.to_dict() returns list with correct keys."""
        with active_tenant(tenant_a):
            _, req = make_requirement(tenant_a, workspace_a, "R-1")
            matrix = vcrm_gen.generate_vcrm(workspace_a.id)

        d = matrix.to_dict()
        assert "rows" in d
        assert isinstance(d["rows"], list)
        if d["rows"]:
            row = d["rows"][0]
            assert "requirement_id" in row
            assert "component_id" in row
            assert "test_case_id" in row
            assert "test_result" in row


# ---------------------------------------------------------------------------
# REQ-L2-TE-013: CSV export (mandatory)
# ---------------------------------------------------------------------------

class TestCSVExport:
    """REQ-L2-TE-013: CSV export is mandatory and must be valid."""

    def test_csv_has_header_row(self, vcrm_gen, tenant_a, workspace_a):
        """CSV output starts with the required header row."""
        with active_tenant(tenant_a):
            csv_str = vcrm_gen.export_vcrm_csv(workspace_a.id)

        reader = csv.reader(io.StringIO(csv_str))
        header = next(reader)
        assert header == ["requirement_id", "component_id", "test_case_id", "test_result"]

    def test_csv_has_data_row_per_requirement(
        self, vcrm_gen, tenant_a, workspace_a
    ):
        """CSV has a data row for each requirement."""
        with active_tenant(tenant_a):
            _, req1 = make_requirement(tenant_a, workspace_a, "R-1")
            _, req2 = make_requirement(tenant_a, workspace_a, "R-2")

            csv_str = vcrm_gen.export_vcrm_csv(workspace_a.id)

        reader = csv.reader(io.StringIO(csv_str))
        header = next(reader)  # skip header
        data_rows = list(reader)
        req_ids_in_csv = {row[0] for row in data_rows}

        assert str(req1.id) in req_ids_in_csv
        assert str(req2.id) in req_ids_in_csv

    def test_csv_is_valid_parseable_csv(self, vcrm_gen, tenant_a, workspace_a):
        """CSV output is parseable without error."""
        with active_tenant(tenant_a):
            make_requirement(tenant_a, workspace_a, "R-1")
            csv_str = vcrm_gen.export_vcrm_csv(workspace_a.id)

        # Should not raise
        rows = list(csv.reader(io.StringIO(csv_str)))
        assert len(rows) >= 1  # at least header

    def test_csv_empty_workspace_is_header_only(
        self, vcrm_gen, tenant_a, workspace_a
    ):
        """Empty workspace produces header-only CSV."""
        with active_tenant(tenant_a):
            csv_str = vcrm_gen.export_vcrm_csv(workspace_a.id)

        rows = list(csv.reader(io.StringIO(csv_str)))
        # Only the header row
        assert len(rows) == 1
        assert rows[0] == ["requirement_id", "component_id", "test_case_id", "test_result"]


# ---------------------------------------------------------------------------
# REQ-L2-TE-013: PDF export (optional)
# ---------------------------------------------------------------------------

class TestPDFExport:
    """REQ-L2-TE-013: PDF export is optional (raises NotImplementedError)."""

    def test_pdf_export_raises_not_implemented(
        self, vcrm_gen, tenant_a, workspace_a
    ):
        """PDF export raises NotImplementedError per ADR-L3-TE4-02."""
        with active_tenant(tenant_a):
            with pytest.raises(NotImplementedError):
                vcrm_gen.export_vcrm_pdf(workspace_a.id)
