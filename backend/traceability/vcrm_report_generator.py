"""
COMP-TE-004 VCRMReportGenerator — Verification Cross Reference Matrix.

leaf_id: COMP-TE-004_VCRMReportGenerator
req_id: REQ-L2-TE-013

Responsibilities:
- Generate VCRM matrix: requirement_id × component_id × test_case_id × test_result
- Filterable by workspace and baseline_id (REQ-L2-TE-013)
- CSV export (mandatory), PDF export (optional / NotImplementedError)
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
from typing import Optional

from persistence.models import ArchitectureElement
from persistence.tenancy import TenantContext

from traceability.coverage_calculator import CoverageCalculator
from traceability.query_engine import QueryEngine
from traceability.types import VCRMMatrix, VCRMRow


class VCRMReportGenerator:
    """COMP-TE-004: Generates Verification Cross Reference Matrix (VCRM).

    ADR-L3-TE4-01: flat matrix (list of VCRMRow), not nested structure.
    ADR-L3-TE4-02: CSV is mandatory; PDF raises NotImplementedError.
    ADR-L3-TE4-03: baseline_id accepted for snapshot comparisons.

    REQ-L2-TE-013
    """

    def __init__(
        self,
        coverage_calculator: Optional[CoverageCalculator] = None,
        query_engine: Optional[QueryEngine] = None,
    ) -> None:
        self._coverage = coverage_calculator or CoverageCalculator()
        self._query_engine = query_engine or QueryEngine()

    # IF-TE-EXT-IN-002
    def generate_vcrm(
        self,
        workspace_id: uuid.UUID,
        baseline_id: Optional[uuid.UUID] = None,
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
        coverage_data = self._coverage.get_coverage_data(
            workspace_id=workspace_id,
            baseline_id=baseline_id,
        )

        if not coverage_data.entries:
            return VCRMMatrix(rows=[])

        # Load component links for each requirement via QueryEngine (IF-TE-INT-005)
        # We query downstream from each requirement artifact to find satisfies/implements links
        tenant_id = TenantContext.get_tenant()

        rows: list[VCRMRow] = []
        for entry in coverage_data.entries:
            req_id = entry.requirement_id

            # Find requirement artifact ID to query components
            # (requirement_id is the Requirement PK; we need artifact_id)
            component_ids = self._get_component_ids_for_requirement(req_id)

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
                            )
                        )

        return VCRMMatrix(rows=rows)

    def export_vcrm_csv(
        self,
        workspace_id: uuid.UUID,
        baseline_id: Optional[uuid.UUID] = None,
    ) -> str:
        """Export the VCRM matrix as a CSV string.

        REQ-L2-TE-013: CSV export is mandatory.
        Returns a valid CSV string with header row.
        """
        matrix = self.generate_vcrm(workspace_id=workspace_id, baseline_id=baseline_id)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["requirement_id", "component_id", "test_case_id", "test_result"])
        for row in matrix.rows:
            writer.writerow([
                row.requirement_id,
                row.component_id,
                row.test_case_id,
                row.test_result,
            ])
        return output.getvalue()

    def export_vcrm_pdf(
        self,
        workspace_id: uuid.UUID,
        baseline_id: Optional[uuid.UUID] = None,
    ) -> bytes:
        """Export the VCRM matrix as a PDF (optional feature).

        REQ-L2-TE-013: PDF export is optional; raises NotImplementedError
        until a template renderer dependency is added.
        ADR-L3-TE4-02: explicitly documented as not implemented.
        """
        raise NotImplementedError(
            "PDF export is not yet implemented. "
            "Use export_vcrm_csv() for the mandatory CSV format."
        )

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _get_component_ids_for_requirement(self, requirement_id: str) -> list[str]:
        """Find ArchitectureElement IDs linked to a requirement via `satisfies`.

        Uses the ORM directly (IF-TE-EXT-OUT-001) to avoid cross-component
        coupling beyond the registered interfaces.
        """
        from django.db import connection

        tenant_id = TenantContext.get_tenant()

        # requirement_id is the Requirement PK; find its artifact_id first
        sql_req_art = """
            SELECT artifact_id FROM pl_requirement
            WHERE id = %s AND tenant_id = %s
        """
        with connection.cursor() as cur:
            cur.execute(sql_req_art, [str(requirement_id), str(tenant_id)])
            row = cur.fetchone()
        if not row:
            return []

        req_artifact_id = str(row[0])

        # Find downstream artifacts linked with satisfies or implements
        sql = """
            SELECT DISTINCT tl.target_id
            FROM pl_tracelink tl
            JOIN pl_artifact a ON a.id = tl.target_id
            WHERE tl.source_id = %s
              AND tl.link_type IN ('satisfies', 'implements')
              AND tl.tenant_id = %s
        """
        with connection.cursor() as cur:
            cur.execute(sql, [req_artifact_id, str(tenant_id)])
            rows = cur.fetchall()

        return [str(r[0]) for r in rows]


__all__ = ["VCRMReportGenerator"]
