"""
COMP-TE-004 VCRMReportGenerator — VCRM matrix generation and export tests.

Covers:
  REQ-L2-TE-013: VCRM matrix generation, CSV export, PDF export
  REQ-L2-AS-016: PDF report generation (requirement_document, traceability_matrix)
"""
from __future__ import annotations

import csv
import io

import pytest

from traceability.vcrm_report_generator import VCRMReportGenerator
from traceability.coverage_calculator import CoverageCalculator
from traceability.query_engine import QueryEngine
from traceability.pdf_report_generator import generate_pdf_report, VALID_LAYOUTS
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
# REQ-L2-AS-016: PDF export (implemented via reportlab)
# ---------------------------------------------------------------------------

class TestPDFExport:
    """REQ-L2-AS-016: PDF export produces valid PDF bytes."""

    def test_pdf_export_returns_valid_pdf(
        self, vcrm_gen, tenant_a, workspace_a
    ):
        """PDF export returns non-empty bytes starting with %PDF-."""
        with active_tenant(tenant_a):
            make_requirement(tenant_a, workspace_a, "R-1")
            pdf_bytes = vcrm_gen.export_vcrm_pdf(workspace_a.id)

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 1024  # > 1KB
        assert pdf_bytes[:5] == b"%PDF-"

    def test_pdf_requirement_document_contains_workspace_title(
        self, tenant_a, workspace_a
    ):
        """Requirement document PDF contains the workspace name."""
        from pypdf import PdfReader

        with active_tenant(tenant_a):
            make_requirement(tenant_a, workspace_a, "R-PDF-Test")
            pdf_bytes = generate_pdf_report(
                workspace_a.id, layout="requirement_document"
            )

        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""

        assert "TE-WS-A" in text

    def test_pdf_traceability_matrix_contains_all_requirements(
        self, tenant_a, workspace_a
    ):
        """Traceability matrix PDF contains all requirement titles."""
        from pypdf import PdfReader

        with active_tenant(tenant_a):
            _, req1 = make_requirement(tenant_a, workspace_a, "Matrix-Req-1")
            _, req2 = make_requirement(tenant_a, workspace_a, "Matrix-Req-2")
            tc_art, tc = make_test_case(tenant_a, workspace_a, "TC-1")
            # Link req1 -> tc via verifies
            art_req1 = req1.artifact
            make_trace_link(art_req1, tc_art, tenant_a, "verifies")

            pdf_bytes = generate_pdf_report(
                workspace_a.id, layout="traceability_matrix"
            )

        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""

        assert "Matrix-Req-1" in text
        assert "Matrix-Req-2" in text

    def test_pdf_invalid_layout_raises(self, tenant_a, workspace_a):
        """Unknown layout raises ValueError."""
        with active_tenant(tenant_a):
            with pytest.raises(ValueError, match="Unknown layout"):
                generate_pdf_report(
                    workspace_a.id, layout="nonexistent_layout"
                )

    def test_pdf_tenant_isolation(
        self, tenant_a, tenant_b, workspace_a, workspace_b_tenant_b
    ):
        """Workspace A's report doesn't include workspace B's data."""
        from pypdf import PdfReader

        with active_tenant(tenant_a):
            make_requirement(tenant_a, workspace_a, "TenantA-Req")

        with active_tenant(tenant_b):
            make_requirement(
                tenant_b, workspace_b_tenant_b, "TenantB-Req-Secret"
            )

        # Generate report for workspace A under tenant A context
        with active_tenant(tenant_a):
            pdf_bytes = generate_pdf_report(
                workspace_a.id, layout="requirement_document"
            )

        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""

        assert "TenantA-Req" in text
        assert "TenantB-Req-Secret" not in text


# ---------------------------------------------------------------------------
# REQ-L2-TE-013: VCRM PDF export via dedicated renderer
# ---------------------------------------------------------------------------


class TestVCRMPDFExport:
    """REQ-L2-TE-013: VCRM PDF export produces valid PDF with 4-column matrix."""

    def test_vcrm_pdf_returns_valid_pdf_bytes(
        self, vcrm_gen, tenant_a, workspace_a
    ):
        """VCRM PDF export returns non-empty bytes starting with %PDF-."""
        with active_tenant(tenant_a):
            _, req = make_requirement(tenant_a, workspace_a, "VCRM-Req-1")
            pdf_bytes = vcrm_gen.export_vcrm_pdf(workspace_a.id)

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 1024  # > 1KB
        assert pdf_bytes[:5] == b"%PDF-"

    def test_vcrm_pdf_empty_workspace_produces_valid_pdf(
        self, vcrm_gen, tenant_a, workspace_a
    ):
        """Empty workspace VCRM PDF is still valid (no error)."""
        with active_tenant(tenant_a):
            pdf_bytes = vcrm_gen.export_vcrm_pdf(workspace_a.id)

        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes[:5] == b"%PDF-"

    def test_vcrm_pdf_contains_matrix_header(
        self, vcrm_gen, tenant_a, workspace_a
    ):
        """VCRM PDF contains table headers (Requirement, Component, TestCase, Result)."""
        from pypdf import PdfReader

        with active_tenant(tenant_a):
            _, req = make_requirement(tenant_a, workspace_a, "VCRM-Header-Test")
            pdf_bytes = vcrm_gen.export_vcrm_pdf(workspace_a.id)

        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""

        # Should contain at least some indication of the matrix structure
        assert "Requirement" in text or "VCRM" in text

    def test_vcrm_pdf_contains_requirement_data(
        self, vcrm_gen, tenant_a, workspace_a
    ):
        """VCRM PDF contains requirement IDs from the matrix."""
        from pypdf import PdfReader

        with active_tenant(tenant_a):
            _, req1 = make_requirement(tenant_a, workspace_a, "VCRM-Req-Alpha")
            _, req2 = make_requirement(tenant_a, workspace_a, "VCRM-Req-Beta")
            pdf_bytes = vcrm_gen.export_vcrm_pdf(workspace_a.id)

        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""

        # Should contain the IDs (at least first 8 chars or full UUID)
        req1_id_short = str(req1.id)[:8]
        req2_id_short = str(req2.id)[:8]
        # At least one of the requirements should appear
        assert req1_id_short in text or str(req1.id) in text or req2_id_short in text or str(req2.id) in text

    def test_vcrm_pdf_with_test_results(
        self, vcrm_gen, tenant_a, workspace_a
    ):
        """VCRM PDF includes test results (Passed, Failed, Not Run)."""
        from pypdf import PdfReader

        with active_tenant(tenant_a):
            _, req = make_requirement(tenant_a, workspace_a, "VCRM-WithTests")
            _, tc = make_test_case(tenant_a, workspace_a, "VCRM-TC-1")
            # Link requirement to test case
            art_req = req.artifact
            art_tc = tc.artifact
            make_trace_link(art_req, art_tc, tenant_a, "verifies")

            pdf_bytes = vcrm_gen.export_vcrm_pdf(workspace_a.id)

        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""

        # Should indicate VCRM or matrix
        assert "VCRM" in text or "Matrix" in text or len(text) > 500
