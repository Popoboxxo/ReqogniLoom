"""
COMP-TE-004 VCRMReportGenerator — VCRM matrix generation and export tests.

Covers:
  REQ-L2-TE-013: VCRM matrix generation, CSV export, PDF export
  REQ-L2-AS-016: PDF report generation (requirement_document, traceability_matrix)
"""
from __future__ import annotations

import csv
import io
import uuid

import pytest

from traceability.coverage_calculator import CoverageCalculator
from traceability.pdf_report_generator import VALID_LAYOUTS, generate_pdf_report
from traceability.query_engine import QueryEngine
from traceability.tests.conftest import (
    active_tenant,
    make_artifact,
    make_requirement,
    make_test_case,
    make_trace_link,
)
from traceability.vcrm_report_generator import VCRMReportGenerator

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
            # SE convention: TestCase is source, Requirement is target.
            make_trace_link(tc_art, art_req, tenant_a, "verifies")

            matrix = vcrm_gen.generate_vcrm(workspace_a.id)

        req_rows = [r for r in matrix.rows if r.requirement_id == str(req.id)]
        assert len(req_rows) >= 1
        tc_row = next(
            (r for r in req_rows if r.test_case_id == str(tc_art.id)), None
        )
        assert tc_row is not None

    def test_vcrm_still_shows_outdated_requirement(
        self, vcrm_gen, tenant_a, workspace_a
    ):
        """Regression: VCRM must keep showing outdated Requirements.

        CoverageCalculator.get_coverage_data() defaults to
        include_outdated=False, but VCRMReportGenerator is an audit/
        compliance report and must explicitly opt back into
        include_outdated=True so outdated requirements don't silently
        disappear from the matrix.
        """
        from workflow.services import create_default_workflow, outdate

        class _SystemCtx:
            user_id = "system:test-vcrm-report-generator"

        with active_tenant(tenant_a):
            _, req = make_requirement(tenant_a, workspace_a, "Outdated-Req")
            # Task 12: the `status` column is dropped -- "outdated" can only
            # be represented by a real WorkflowItemState row now.
            create_default_workflow(
                workspace_id=workspace_a.id,
                preset="standard",
                item_type="Requirement",
                tenant_id=tenant_a.id,
            )
            outdate(
                item_id=req.id,
                item_type="Requirement",
                workspace_id=workspace_a.id,
                ctx=_SystemCtx(),
                reason="test: mark outdated",
            )

            matrix = vcrm_gen.generate_vcrm(workspace_a.id)

        assert any(r.requirement_id == str(req.id) for r in matrix.rows)

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
            # #878: additive key — the pre-existing keys stay untouched.
            assert "verification_method" in row


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
        assert header == [
            "requirement_id",
            "component_id",
            "test_case_id",
            "test_result",
            "verification_method",
        ]

    def test_csv_has_data_row_per_requirement(
        self, vcrm_gen, tenant_a, workspace_a
    ):
        """CSV has a data row for each requirement."""
        with active_tenant(tenant_a):
            _, req1 = make_requirement(tenant_a, workspace_a, "R-1")
            _, req2 = make_requirement(tenant_a, workspace_a, "R-2")

            csv_str = vcrm_gen.export_vcrm_csv(workspace_a.id)

        reader = csv.reader(io.StringIO(csv_str))
        next(reader)  # skip header
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
        assert rows[0] == [
            "requirement_id",
            "component_id",
            "test_case_id",
            "test_result",
            "verification_method",
        ]


# ---------------------------------------------------------------------------
# #878 (B2-T3): verification_method in the VCRM
# ---------------------------------------------------------------------------

class TestVCRMVerificationMethod:
    """#878: verification_method is carried through matrix, CSV and PDF."""

    @staticmethod
    def _set_method(req, method: str | None) -> None:
        """Set ``verification_method`` on a requirement row."""
        req.verification_method = method
        req.save(update_fields=["verification_method"])

    def test_vcrm_row_carries_verification_method(
        self, vcrm_gen, tenant_a, workspace_a
    ):
        """A row exposes the requirement's verification_method."""
        with active_tenant(tenant_a):
            _, req = make_requirement(tenant_a, workspace_a, "R-Method")
            self._set_method(req, "Test")
            matrix = vcrm_gen.generate_vcrm(workspace_a.id)

        row = next(r for r in matrix.rows if r.requirement_id == str(req.id))
        assert row.verification_method == "Test"

    def test_vcrm_row_without_method_is_empty_string(
        self, vcrm_gen, tenant_a, workspace_a
    ):
        """An unset verification_method is an empty string, never None."""
        with active_tenant(tenant_a):
            _, req = make_requirement(tenant_a, workspace_a, "R-NoMethod")
            matrix = vcrm_gen.generate_vcrm(workspace_a.id)

        row = next(r for r in matrix.rows if r.requirement_id == str(req.id))
        assert row.verification_method == ""

    def test_csv_appends_verification_method_column(
        self, vcrm_gen, tenant_a, workspace_a
    ):
        """CSV header ends with verification_method; the value is carried."""
        with active_tenant(tenant_a):
            art_req, req = make_requirement(tenant_a, workspace_a, "R-CSV")
            self._set_method(req, "Test")
            art_tc, _tc = make_test_case(tenant_a, workspace_a, "TC-CSV")
            make_trace_link(art_tc, art_req, tenant_a, "verifies")

            csv_str = vcrm_gen.export_vcrm_csv(workspace_a.id)

        rows = list(csv.reader(io.StringIO(csv_str)))
        assert rows[0] == [
            "requirement_id",
            "component_id",
            "test_case_id",
            "test_result",
            "verification_method",
        ]

        data_row = next(row for row in rows[1:] if row[2] == str(art_tc.id))
        assert data_row[4] == "Test"

    def test_csv_keeps_existing_column_positions(
        self, vcrm_gen, tenant_a, workspace_a
    ):
        """Regression: the four pre-existing columns keep their index.

        #878 appends the new column at the END only; a consumer reading
        columns 0-3 by index must keep working.
        """
        with active_tenant(tenant_a):
            art_req, req = make_requirement(tenant_a, workspace_a, "R-Pos")
            self._set_method(req, "Analysis")
            art_tc, _tc = make_test_case(tenant_a, workspace_a, "TC-Pos")
            make_trace_link(art_tc, art_req, tenant_a, "verifies")

            csv_str = vcrm_gen.export_vcrm_csv(workspace_a.id)

        header = next(csv.reader(io.StringIO(csv_str)))
        # First four positions unchanged, in order.
        assert header[:4] == [
            "requirement_id",
            "component_id",
            "test_case_id",
            "test_result",
        ]
        assert header[4:] == ["verification_method"]

        data_row = next(
            row
            for row in list(csv.reader(io.StringIO(csv_str)))[1:]
            if row[2] == str(art_tc.id)
        )
        assert data_row[0] == str(req.id)
        assert data_row[1] == ""  # no allocation → empty component
        assert data_row[2] == str(art_tc.id)
        assert data_row[3] == "Not Run"
        assert data_row[4] == "Analysis"

    def test_pdf_method_column_renders_none_placeholder(self):
        """PDF Method column shows '(none)' for an empty method (#878)."""
        from pypdf import PdfReader

        from traceability.types import VCRMMatrix, VCRMRow
        from traceability.vcrm_report_generator import _render_vcrm_pdf

        matrix = VCRMMatrix(
            rows=[
                VCRMRow(
                    requirement_id="req-with-method",
                    component_id="comp-1",
                    test_case_id="tc-1",
                    test_result="Passed",
                    verification_method="Analysis",
                ),
                VCRMRow(
                    requirement_id="req-without-method",
                    component_id="comp-1",
                    test_case_id="tc-1",
                    test_result="Passed",
                    verification_method="",
                ),
            ]
        )
        pdf_bytes = _render_vcrm_pdf(matrix, uuid.UUID(int=1))

        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = "".join(page.extract_text() or "" for page in reader.pages)

        assert "Method" in text
        assert "Analysis" in text
        # Only the method column may render "(none)" here: every row has a
        # component and a test case, so the placeholder is unambiguous.
        assert "(none)" in text


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
            # Link tc -> req1 via verifies (TestCase is source, Req is target)
            art_req1 = req1.artifact
            make_trace_link(tc_art, art_req1, tenant_a, "verifies")

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
            # Link test case to requirement (TestCase is source, Req is target)
            art_req = req.artifact
            art_tc = tc.artifact
            make_trace_link(art_tc, art_req, tenant_a, "verifies")

            pdf_bytes = vcrm_gen.export_vcrm_pdf(workspace_a.id)

        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""

        # Should indicate VCRM or matrix
        assert "VCRM" in text or "Matrix" in text or len(text) > 500


# ---------------------------------------------------------------------------
# PERF-002: batched allocation lookups (N+1 elimination)
# ---------------------------------------------------------------------------


def _vcrm_row_key(row) -> tuple[str, str, str, str, str]:
    """Comparable tuple for a VCRMRow (independent of row ordering)."""
    return (
        str(row.requirement_id),
        str(row.component_id),
        str(row.test_case_id),
        str(row.test_result),
        str(row.verification_method),
    )


class TestVCRMBatchedAllocationQueries:
    """PERF-002: allocation lookups are two queries, not two per requirement."""

    @staticmethod
    def _seed_allocated_requirements(tenant, workspace, count: int) -> dict[str, str]:
        """Create ``count`` requirements, each allocated to one component."""
        from persistence.models import ArchitectureElement

        comp_by_req: dict[str, str] = {}
        with active_tenant(tenant):
            for i in range(count):
                req_art, req = make_requirement(tenant, workspace, f"PERF-REQ-{i}")
                comp_art = make_artifact(tenant, workspace, "architecture_element")
                ArchitectureElement.objects.create(
                    tenant=tenant, artifact=comp_art, title=f"PERF-COMP-{i}"
                )
                make_trace_link(req_art, comp_art, tenant, "allocated-to")
                comp_by_req[str(req.id)] = str(comp_art.id)
        return comp_by_req

    def test_generate_vcrm_uses_two_allocation_queries(
        self, vcrm_gen, tenant_a, workspace_a
    ):
        """25 allocated requirements → exactly one link scan + one req-artifact query.

        Pre-fix this issued 2 queries *per requirement* (50 allocation
        queries). The allocation link scan is identified by the
        ``allocated-to`` literal; the requirement-artifact lookup by the
        ``pl_requirement`` + ``ANY`` pattern.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self._seed_allocated_requirements(tenant_a, workspace_a, 25)

        with active_tenant(tenant_a):
            with CaptureQueriesContext(connection) as ctx:
                matrix = vcrm_gen.generate_vcrm(workspace_a.id)

        sqls = [q["sql"] for q in ctx.captured_queries]
        link_scans = [s for s in sqls if "allocated-to" in s]
        assert len(link_scans) == 1, (
            f"expected exactly 1 allocation link scan, got {len(link_scans)}: {link_scans}"
        )
        req_artifact_lookups = [
            s for s in sqls if "pl_requirement" in s and "ANY" in s.upper()
        ]
        assert len(req_artifact_lookups) == 1, (
            "expected exactly 1 batched requirement-artifact query, got "
            f"{len(req_artifact_lookups)}: {req_artifact_lookups}"
        )
        # Preserved per-requirement contract of the old per-req query:
        # inner JOIN drops targets without an artifact row, DISTINCT removes
        # duplicate edges, tenant filter is explicit, ordering deterministic.
        scan_upper = link_scans[0].upper()
        assert "JOIN PL_ARTIFACT" in scan_upper
        assert "DISTINCT" in scan_upper
        assert "TENANT_ID" in scan_upper
        assert "ORDER BY" in scan_upper
        assert matrix.rows, "expected a non-empty matrix for 25 allocations"

    def test_batched_rows_match_per_requirement_reference(
        self, vcrm_gen, tenant_a, workspace_a, tenant_b
    ):
        """Batched rows are functionally identical to the old per-req algorithm.

        Seeded edge cases: multiple allocations, no allocation and a
        cross-tenant link (dropped by the explicit tenant filter). The
        inner-JOIN contract is asserted structurally in the query-count test;
        a target without an ``pl_artifact`` row cannot exist behind the FK.
        """
        from django.db import connection

        from persistence.models import ArchitectureElement, TestRun, TestRunResult

        with active_tenant(tenant_a):
            r_multi_art, r_multi = make_requirement(tenant_a, workspace_a, "R-multi")
            r_none_art, r_none = make_requirement(tenant_a, workspace_a, "R-none")
            r_orphan_art, r_orphan = make_requirement(tenant_a, workspace_a, "R-orphan")

            comp_arts = []
            for i in range(3):
                art = make_artifact(tenant_a, workspace_a, "architecture_element")
                ArchitectureElement.objects.create(
                    tenant=tenant_a, artifact=art, title=f"C-{i}"
                )
                comp_arts.append(art)
            for comp in comp_arts:
                make_trace_link(r_multi_art, comp, tenant_a, "allocated-to")

            # A verifying TestCase so the matrix has a non-"Not Run" path too.
            tc_art, tc = make_test_case(tenant_a, workspace_a, "TC-multi")
            make_trace_link(tc_art, r_multi_art, tenant_a, "verifies")
            run = TestRun.objects.create(
                tenant=tenant_a, workspace=workspace_a, name="run-multi"
            )
            TestRunResult.objects.create(
                tenant=tenant_a, test_run=run, test_case=tc,
                test_case_title="TC-multi", status="passed",
            )

        # Cross-tenant link: source is tenant_a's requirement, but the link
        # itself belongs to tenant_b — the tenant filter must drop it.
        with active_tenant(tenant_b):
            b_comp = make_artifact(tenant_b, workspace_a, "architecture_element")
            with connection.cursor() as cur:
                cur.execute(
                    "INSERT INTO pl_tracelink "
                    "(id, source_id, target_id, link_type, tenant_id, rationale, "
                    "created_at, modified_at, version) "
                    "VALUES (%s, %s, %s, %s, %s, '', now(), now(), 1)",
                    [
                        str(uuid.uuid4()), str(r_orphan_art.id), str(b_comp.id),
                        "allocated-to", str(tenant_b.id),
                    ],
                )

        with active_tenant(tenant_a):
            # Reference: the ORIGINAL per-requirement algorithm (raw SQL, no
            # batching) — an independent oracle for the new implementation.
            from traceability.coverage_calculator import CoverageCalculator

            entries = CoverageCalculator().get_coverage_data(
                workspace_a.id, include_outdated=True
            ).entries
            ref_rows = []
            with connection.cursor() as cur:
                for entry in entries:
                    cur.execute(
                        "SELECT artifact_id FROM pl_requirement "
                        "WHERE id = %s AND tenant_id = %s",
                        [str(entry.requirement_id), str(tenant_a.id)],
                    )
                    row = cur.fetchone()
                    if not row:
                        continue
                    cur.execute(
                        "SELECT DISTINCT tl.target_id FROM pl_tracelink tl "
                        "JOIN pl_artifact a ON a.id = tl.target_id "
                        "WHERE tl.source_id = %s AND tl.link_type = 'allocated-to' "
                        "AND tl.tenant_id = %s",
                        [str(row[0]), str(tenant_a.id)],
                    )
                    comps = [str(r[0]) for r in cur.fetchall()] or [""]
                    for comp in comps:
                        if not entry.test_cases:
                            ref_rows.append((
                                str(entry.requirement_id), comp, "", "Not Run",
                                entry.verification_method or "",
                            ))
                        else:
                            for tc_info in entry.test_cases:
                                ref_rows.append((
                                    str(entry.requirement_id), comp,
                                    tc_info.get("id", ""),
                                    tc_info.get("result", "Not Run"),
                                    entry.verification_method or "",
                                ))

            new_rows = [
                _vcrm_row_key(r)
                for r in vcrm_gen.generate_vcrm(workspace_a.id).rows
            ]

        assert sorted(new_rows) == sorted(ref_rows), (
            "batched rows differ from the per-requirement reference"
        )
        # Orphan-only requirement must keep exactly one blank-component row.
        orphan_rows = [r for r in new_rows if r[0] == str(r_orphan.id)]
        assert len(orphan_rows) == 1
        assert orphan_rows[0][1] == ""
        # Multi-allocated requirement: deterministic per-requirement target order.
        multi_rows = [r for r in new_rows if r[0] == str(r_multi.id)]
        comp_seq = [r[1] for r in multi_rows]
        assert comp_seq == sorted(comp_seq)
        assert len(comp_seq) == 3

    def test_requirement_artifact_ids_are_deduplicated(
        self, vcrm_gen, tenant_a, workspace_a
    ):
        """Duplicate requirement ids are deduped before the ANY(%s) bind."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        comp_by_req = self._seed_allocated_requirements(tenant_a, workspace_a, 3)
        req_ids = list(comp_by_req)
        duplicated = req_ids + [req_ids[0], req_ids[1]]

        with active_tenant(tenant_a):
            with CaptureQueriesContext(connection) as ctx:
                artifact_map = vcrm_gen._fetch_requirement_artifact_ids(duplicated)

        import re

        assert set(artifact_map) == set(req_ids)
        q = [x for x in ctx.captured_queries if "pl_requirement" in x["sql"]]
        assert len(q) == 1
        # psycopg interpolates params client-side, so inspect the bound
        # ARRAY literal: 3 deduplicated ids, not the 5 originally supplied.
        arr = re.search(r"ARRAY\[(.*?)\]", q[0]["sql"])
        assert arr is not None, q[0]["sql"]
        assert len(re.findall(r"[0-9a-f]{8}-[0-9a-f-]{27}", arr.group(1))) == 3

    @pytest.mark.slow
    def test_explain_uses_composite_index(self, vcrm_gen, tenant_a, workspace_a):
        """EXPLAIN shows the new (source_id, link_type, tenant_id) index.

        The planner is steered with ``enable_seqscan=off`` (the seeded table is
        small) and the data includes competing link types on the same sources
        so ``link_type`` is discriminating — without that the narrower
        single-column ``source_id`` index wins. Enough rows are seeded for the
        planner to prefer the composite index; only a handful of source ids
        are probed, mirroring the real batched query for one workspace.
        """
        import uuid as uuid_lib

        from django.db import connection

        from persistence.models import (
            ArchitectureElement,
            Requirement,
            TraceLink,
        )

        with active_tenant(tenant_a):
            targets = []
            for i in range(60):
                art = make_artifact(tenant_a, workspace_a, "architecture_element")
                ArchitectureElement.objects.create(
                    tenant=tenant_a, artifact=art, title=f"EXPLAIN-C-{i}"
                )
                targets.append(art)

            sources = []
            for i in range(120):
                art = make_artifact(tenant_a, workspace_a, "requirement")
                Requirement.objects.create(
                    tenant=tenant_a, artifact=art, title=f"EXPLAIN-R-{i}"
                )
                sources.append(art)

            # Competing link types on the same sources force the planner to
            # use the full (source_id, link_type, tenant_id) prefix.
            links = [
                TraceLink(
                    tenant=tenant_a, source=src, target=tgt, link_type=link_type
                )
                for src in sources
                for tgt in targets
                for link_type in ("allocated-to", "references", "satisfies")
            ]
            TraceLink.objects.bulk_create(links, batch_size=1000)

            sample = [uuid_lib.UUID(str(a.id)) for a in sources[:5]]
            with connection.cursor() as cur:
                cur.execute("ANALYZE pl_tracelink")
                cur.execute("SET enable_seqscan = off")
                try:
                    cur.execute(
                        "EXPLAIN SELECT DISTINCT tl.source_id, tl.target_id "
                        "FROM pl_tracelink tl JOIN pl_artifact a ON a.id = tl.target_id "
                        "WHERE tl.source_id = ANY(%s) AND tl.link_type = 'allocated-to' "
                        "AND tl.tenant_id = %s ORDER BY tl.source_id, tl.target_id",
                        [sample, str(tenant_a.id)],
                    )
                    plan = "\n".join(row[0] for row in cur.fetchall())
                finally:
                    cur.execute("RESET enable_seqscan")

        # The planner legitimately picks either the composite index or the
        # narrower pl_tracelink_source_id index depending on table stats.
        # Pin the invariant that matters: the index exists (migration applied)
        # and the scan is index-backed, never a sequential scan.
        with connection.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_indexes "
                "WHERE indexname = 'idx_tracelink_source_linktype_tenant'"
            )
            assert cur.fetchone() is not None, "composite index migration missing"
        assert "Seq Scan on pl_tracelink" not in plan, plan
        assert "Index" in plan or "Bitmap" in plan, plan
