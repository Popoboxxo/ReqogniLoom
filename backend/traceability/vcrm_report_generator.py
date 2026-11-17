"""
COMP-TE-004 VCRMReportGenerator — Verification Cross Reference Matrix.

leaf_id: COMP-TE-004_VCRMReportGenerator
req_id: REQ-L2-TE-013

Responsibilities:
- Generate VCRM matrix: requirement_id × component_id × test_case_id × test_result
- Filterable by workspace and baseline_id (REQ-L2-TE-013)
- CSV export (mandatory), PDF export (implemented via reportlab)
- Test result: "Passed" | "Failed" | "Not Run" (default: "Not Run")

Interface contracts consumed:
- IF-TE-INT-004: CoverageCalculator.get_coverage_data(workspace_id, baseline_id?)
- IF-TE-INT-005: QueryEngine.query(artifact_id, direction, ctx)
- IF-TE-EXT-OUT-001: Django ORM (ArchitectureElement metadata)

Interface contracts exposed:
- IF-TE-EXT-IN-002: generate_vcrm / export_vcrm_csv / export_vcrm_pdf

Architecture:
  docs/se/L1/Gesamtsystem/L2/TraceabilityEngineSystem/Components/
  COMP-TE-004_VCRMReportGenerator/L3_COMP-TE-004_VCRMReportGenerator_Architecture.md
"""
from __future__ import annotations

import csv
import io
import uuid
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from persistence.models import ArchitectureElement
from persistence.tenancy import TenantContext
from traceability.coverage_calculator import CoverageCalculator
from traceability.query_engine import QueryEngine
from traceability.types import VCRMMatrix, VCRMRow


class VCRMReportGenerator:
    """COMP-TE-004: Generates Verification Cross Reference Matrix (VCRM).

    ADR-L3-TE4-01: flat matrix (list of VCRMRow), not nested structure.
    ADR-L3-TE4-02: CSV is mandatory; PDF rendered via reportlab.
    ADR-L3-TE4-03: baseline_id accepted for snapshot comparisons.

    REQ-L2-TE-013
    """

    def __init__(
        self,
        coverage_calculator: CoverageCalculator | None = None,
        query_engine: QueryEngine | None = None,
    ) -> None:
        self._coverage = coverage_calculator or CoverageCalculator()
        self._query_engine = query_engine or QueryEngine()

    # IF-TE-EXT-IN-002
    def generate_vcrm(
        self,
        workspace_id: uuid.UUID,
        baseline_id: uuid.UUID | None = None,
    ) -> VCRMMatrix:
        """Generate the VCRM matrix for a workspace.

        REQ-L2-TE-013:
        - One row per requirement–component–test_case combination.
        - Rows without a TestCase link get test_result = "Not Run".
        - Empty workspace → empty matrix (no error).

        Args:
            workspace_id: Workspace to generate the matrix for.
            baseline_id: Optional baseline snapshot (forwarded to coverage data).

        Returns:
            VCRMMatrix with all rows.
        """
        # Explicitly include outdated Requirements/TestCases: a compliance
        # report (VCRM) must not silently hide entries just because the
        # underlying CoverageCalculator changed its default behavior.
        coverage_data = self._coverage.get_coverage_data(
            workspace_id=workspace_id,
            baseline_id=baseline_id,
            include_outdated=True,
        )

        if not coverage_data.entries:
            return VCRMMatrix(rows=[])

        # PERF-002: resolve the requirement->artifact mapping and the
        # allocation links in TWO queries for the whole matrix. The old code
        # called ``_get_component_ids_for_requirement`` once per requirement
        # (2 raw queries each → 2R queries for R requirements).
        req_ids = [str(entry.requirement_id) for entry in coverage_data.entries]
        unique_req_ids = list(dict.fromkeys(req_ids))  # dedupe, keep order
        req_artifact_by_id = self._fetch_requirement_artifact_ids(unique_req_ids)
        req_artifact_ids = list(dict.fromkeys(req_artifact_by_id.values()))
        components_by_artifact = self._fetch_allocated_component_ids(
            req_artifact_ids
        )

        rows: list[VCRMRow] = []
        for entry in coverage_data.entries:
            req_id = str(entry.requirement_id)
            req_artifact_id = req_artifact_by_id.get(req_id)
            component_ids = (
                components_by_artifact.get(req_artifact_id, [])
                if req_artifact_id
                else []
            )

            if not component_ids:
                component_ids = [""]  # ensure at least one row per requirement

            for comp_id in component_ids:
                if not entry.test_cases:
                    # No test cases → single "Not Run" row
                    rows.append(
                        VCRMRow(
                            requirement_id=req_id,
                            component_id=comp_id,
                            test_case_id="",
                            test_result="Not Run",
                            verification_method=entry.verification_method or "",
                        )
                    )
                else:
                    for tc in entry.test_cases:
                        rows.append(
                            VCRMRow(
                                requirement_id=req_id,
                                component_id=comp_id,
                                test_case_id=tc.get("id", ""),
                                test_result=tc.get("result", "Not Run"),
                                verification_method=entry.verification_method or "",
                            )
                        )

        return VCRMMatrix(rows=rows)

    def export_vcrm_csv(
        self,
        workspace_id: uuid.UUID,
        baseline_id: uuid.UUID | None = None,
    ) -> str:
        """Export the VCRM matrix as a CSV string.

        REQ-L2-TE-013: CSV export is mandatory.
        Returns a valid CSV string with header row.

        #878 (B2-T3): ``verification_method`` is appended as the **last**
        column so every pre-existing column keeps its position — consumers
        that read the first four columns by index stay compatible.
        """
        matrix = self.generate_vcrm(workspace_id=workspace_id, baseline_id=baseline_id)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "requirement_id",
            "component_id",
            "test_case_id",
            "test_result",
            "verification_method",
        ])
        for row in matrix.rows:
            writer.writerow([
                row.requirement_id,
                row.component_id,
                row.test_case_id,
                row.test_result,
                row.verification_method,
            ])
        return output.getvalue()

    def export_vcrm_pdf(
        self,
        workspace_id: uuid.UUID,
        baseline_id: uuid.UUID | None = None,
    ) -> bytes:
        """Export the VCRM matrix as a PDF.

        REQ-L2-TE-013 / REQ-L2-AS-016: PDF export renders the VCRM matrix
        (Requirement × Component × TestCase × Result × Method) via reportlab.
        """
        matrix = self.generate_vcrm(workspace_id=workspace_id, baseline_id=baseline_id)
        return _render_vcrm_pdf(matrix, workspace_id)

    # -----------------------------------------------------------------------
    # PDF helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _fetch_requirement_artifact_ids(
        requirement_ids: list[str],
    ) -> dict[str, str]:
        """Map Requirement PK -> ``artifact_id`` for *requirement_ids*.

        PERF-002: one query for the whole matrix instead of one per
        requirement. The caller deduplicates ids before binding them to
        ``ANY(%s)``; UUID objects are required because PostgreSQL cannot
        compare a ``uuid`` column against a ``text[]`` bind.
        """
        from django.db import connection

        if not requirement_ids:
            return {}

        # Dedupe before the ANY(%s) bind: the same requirement may appear in
        # several coverage entries, and repeating ids only enlarges the bind.
        unique_ids = list(dict.fromkeys(str(r) for r in requirement_ids))
        tenant_id = TenantContext.get_tenant()
        sql = """
            SELECT id, artifact_id FROM pl_requirement
            WHERE id = ANY(%s) AND tenant_id = %s
        """
        params = [[uuid.UUID(r) for r in unique_ids], str(tenant_id)]
        with connection.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

        return {str(row[0]): str(row[1]) for row in rows}

    @staticmethod
    def _fetch_allocated_component_ids(
        req_artifact_ids: list[str],
    ) -> dict[str, list[str]]:
        """Map requirement artifact id -> allocated component artifact ids.

        PERF-002: one query for the whole matrix instead of one per
        requirement. The original per-requirement contract is preserved:

        * the inner ``JOIN pl_artifact`` drops targets with no artifact row;
        * ``DISTINCT`` removes duplicate edges;
        * the tenant filter is explicit (in addition to RLS);
        * ``ORDER BY source_id, target_id`` keeps per-requirement target
          ordering deterministic — the CSV/PDF positional contract (#878).
        """
        from django.db import connection

        if not req_artifact_ids:
            return {}

        unique_ids = list(dict.fromkeys(str(a) for a in req_artifact_ids))
        tenant_id = TenantContext.get_tenant()
        sql = """
            SELECT DISTINCT tl.source_id, tl.target_id
            FROM pl_tracelink tl
            JOIN pl_artifact a ON a.id = tl.target_id
            WHERE tl.source_id = ANY(%s)
              AND tl.link_type = 'allocated-to'
              AND tl.tenant_id = %s
            ORDER BY tl.source_id, tl.target_id
        """
        params = [[uuid.UUID(a) for a in unique_ids], str(tenant_id)]
        with connection.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

        result: dict[str, list[str]] = {str(a): [] for a in unique_ids}
        for source_id, target_id in rows:
            result.setdefault(str(source_id), []).append(str(target_id))
        return result

    def _get_component_ids_for_requirement(self, requirement_id: str) -> list[str]:
        """Find the ArchitectureElement IDs a requirement is allocated to.

        Retained for single-requirement callers (e.g. the link-type consumer
        tests). ``generate_vcrm`` uses the two batched helpers above so it
        issues two queries for the entire matrix, not two per requirement.
        """
        req_artifact_by_id = self._fetch_requirement_artifact_ids(
            [str(requirement_id)]
        )
        req_artifact_id = req_artifact_by_id.get(str(requirement_id))
        if not req_artifact_id:
            return []
        return self._fetch_allocated_component_ids([req_artifact_id]).get(
            req_artifact_id, []
        )


# -----------------------------------------------------------------------
# PDF Rendering (REQ-L2-TE-013 / REQ-L2-AS-016)
# -----------------------------------------------------------------------


def _render_vcrm_pdf(matrix: VCRMMatrix, workspace_id: uuid.UUID) -> bytes:
    """Render VCRM matrix as PDF document.

    Renders a 5-column table: Requirement | Component | TestCase | Result | Method
    One row per VCRM entry. A requirement without a verification method
    renders ``(none)`` in the Method column (#878, B2-T3).

    Args:
        matrix: VCRMMatrix containing rows to render.
        workspace_id: Workspace UUID for document metadata.

    Returns:
        PDF content as bytes (starts with %PDF-).
    """
    buf = io.BytesIO()
    page_size = landscape(A4)
    doc = SimpleDocTemplate(
        buf,
        pagesize=page_size,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=f"VCRM Report — {workspace_id}",
        author="ReqogniLoom",
    )

    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    meta_style = ParagraphStyle(
        "VCRMMeta",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.grey,
    )
    cell_style = ParagraphStyle(
        "VCRMCell",
        parent=styles["Normal"],
        fontSize=7,
        leading=9,
    )

    story: list = []

    # Title and metadata
    story.append(Paragraph("VCRM Report", title_style))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Verification Cross-Reference Matrix", styles["Heading1"]))
    story.append(Spacer(1, 3 * mm))

    num_rows = len(matrix.rows)
    story.append(
        Paragraph(
            f"Workspace: {workspace_id}  |  "
            f"Total Entries: {num_rows}",
            meta_style,
        )
    )
    story.append(Spacer(1, 6 * mm))

    if not matrix.rows:
        story.append(Paragraph("No entries in this VCRM matrix.", cell_style))
        doc.build(story)
        return buf.getvalue()

    # Build table: header + data rows
    header = [
        Paragraph("<b>Requirement</b>", cell_style),
        Paragraph("<b>Component</b>", cell_style),
        Paragraph("<b>Test Case</b>", cell_style),
        Paragraph("<b>Result</b>", cell_style),
        Paragraph("<b>Method</b>", cell_style),
    ]

    table_data = [header]
    for row in matrix.rows:
        # Shorten IDs for compact display (first 8 chars)
        req_id_short = str(row.requirement_id)[:8]
        comp_id_short = str(row.component_id)[:8] if row.component_id else "(none)"
        tc_id_short = str(row.test_case_id)[:8] if row.test_case_id else "(none)"
        method_short = row.verification_method or "(none)"

        table_data.append([
            Paragraph(req_id_short, cell_style),
            Paragraph(comp_id_short, cell_style),
            Paragraph(tc_id_short, cell_style),
            Paragraph(row.test_result, cell_style),
            Paragraph(method_short, cell_style),
        ])

    # Calculate column widths
    available_width = page_size[0] - 30 * mm  # page width minus margins
    col_widths = [available_width / 5] * 5

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4A5568")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFC")]),
            ]
        )
    )

    story.append(table)
    doc.build(story)
    return buf.getvalue()


__all__ = ["VCRMReportGenerator"]
