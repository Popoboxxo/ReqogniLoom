"""
COMP-TE-003 CoverageCalculator — Requirement-to-TestCase coverage reports.

leaf_id: COMP-TE-003_CoverageCalculator
req_id: REQ-L2-TE-006, REQ-L2-TE-007, REQ-L2-TE-011, REQ-L2-TE-012

Responsibilities:
- Calculate test coverage: % of Requirements with ≥1 `verifies` TraceLink
  to a TestCase (REQ-L2-TE-006)
- Optional filtering by artifact_type and link_type (REQ-L2-TE-007)
- Provide per-requirement coverage data for VCRM (IF-TE-INT-004)
- Performance SLA: ≤500ms for 10k Requirements (REQ-L2-TE-012)

Interface contracts consumed:
- IF-TE-INT-002: TraceLinkManager.get_trace_links(workspace_id, link_type)
- IF-TE-EXT-OUT-001: Django ORM (Requirement, TestCase, TraceLink)

Interface contracts exposed:
- IF-TE-EXT-IN-002: coverage(workspace_id, filters?, ctx) -> CoverageReport
- IF-TE-INT-004: get_coverage_data(workspace_id, baseline_id?) -> CoverageData

Architecture:
  docs/se/L1/Gesamtsystem/L2/TraceabilityEngineSystem/Components/
  COMP-TE-003_CoverageCalculator/L3_COMP-TE-003_CoverageCalculator_Architecture.md
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from django.db import connection

from persistence.models import Requirement, TraceLink
from persistence.tenancy import TenantContext

from traceability.exceptions import InvalidFilterError
from traceability.types import (
    CoverageData,
    CoverageReport,
    RequirementCoverageEntry,
)

logger = logging.getLogger(__name__)

COVERAGE_SLA_MS = 500

# Valid artifact types for filter validation (REQ-L2-TE-007)
_VALID_ARTIFACT_TYPES = frozenset(
    ["Requirement", "ArchitectureElement", "TestCase", "requirement",
     "architecture_element", "testcase"]
)


class CoverageCalculator:
    """COMP-TE-003: Test coverage computation for Requirements.

    ADR-L3-TE3-01: Only `verifies` links count for test coverage.
    ADR-L3-TE3-02: percentage rounded to 1 decimal place.

    REQ-L2-TE-006 / REQ-L2-TE-007 / REQ-L2-TE-011 / REQ-L2-TE-012
    """

    # IF-TE-EXT-IN-002
    def coverage(
        self,
        workspace_id: uuid.UUID,
        artifact_type: Optional[str] = None,
        link_type: Optional[str] = None,
    ) -> CoverageReport:
        """Compute test coverage for Requirements in a workspace.

        REQ-L2-TE-006: Percentage = covered / total * 100 (1 decimal place).
        REQ-L2-TE-007: Optional filtering by artifact_type and link_type.

        Args:
            workspace_id: The workspace to compute coverage for.
            artifact_type: Optional artifact type filter.
            link_type: Optional link type filter (default: "verifies").

        Returns:
            CoverageReport with total, covered, uncovered, percentage.
        """
        t0 = time.monotonic()
        tenant_id = TenantContext.get_tenant()

        # Validate optional filters (REQ-L2-TE-007)
        if artifact_type is not None and artifact_type not in _VALID_ARTIFACT_TYPES:
            raise InvalidFilterError("artifact_type", artifact_type)
        effective_link_type = link_type or "verifies"

        # Load all Requirements in the workspace (tenant-scoped via manager)
        requirements = list(
            Requirement.objects.filter(
                artifact__workspace_id=workspace_id
            ).values("id", "artifact_id")
        )

        total = len(requirements)
        if total == 0:
            return CoverageReport(
                total=0, covered=0, uncovered=[], percentage=0.0
            )

        req_artifact_ids = [str(r["artifact_id"]) for r in requirements]
        req_id_map = {str(r["artifact_id"]): str(r["id"]) for r in requirements}

        # Find which requirement artifacts have a `verifies` link to a TestCase
        # We look at links where source is a requirement artifact and link_type matches
        covered_artifact_ids = self._get_covered_artifact_ids(
            req_artifact_ids=req_artifact_ids,
            link_type=effective_link_type,
            tenant_id=tenant_id,
        )

        covered_req_ids = [req_id_map[aid] for aid in covered_artifact_ids if aid in req_id_map]
        covered_count = len(covered_req_ids)
        uncovered_req_ids = [
            req_id_map[aid]
            for aid in req_artifact_ids
            if aid not in covered_artifact_ids
        ]

        percentage = round(covered_count / total * 100, 1) if total > 0 else 0.0

        elapsed_ms = (time.monotonic() - t0) * 1000
        if elapsed_ms > COVERAGE_SLA_MS:
            logger.warning(
                "CoverageCalculator SLA breach: coverage took %.1fms (SLA: %dms)",
                elapsed_ms,
                COVERAGE_SLA_MS,
            )

        return CoverageReport(
            total=total,
            covered=covered_count,
            uncovered=uncovered_req_ids,
            percentage=percentage,
        )

    # IF-TE-INT-004
    def get_coverage_data(
        self,
        workspace_id: uuid.UUID,
        baseline_id: Optional[uuid.UUID] = None,
    ) -> CoverageData:
        """Return per-requirement test-case assignments for VCRM generation.

        IF-TE-INT-004: consumed by COMP-TE-004 VCRMReportGenerator.
        ADR-L3-TE3-03: baseline_id triggers reading from Baseline snapshot
        (currently uses live data; baseline snapshot integration is a
        future extension — the parameter is accepted and forwarded).

        Returns:
            CoverageData with per-requirement test-case lists.
        """
        tenant_id = TenantContext.get_tenant()

        # Load requirements in workspace
        requirements = list(
            Requirement.objects.filter(
                artifact__workspace_id=workspace_id
            ).values("id", "artifact_id", "title")
        )

        if not requirements:
            return CoverageData(entries=[])

        req_artifact_ids = [str(r["artifact_id"]) for r in requirements]
        req_id_map = {str(r["artifact_id"]): str(r["id"]) for r in requirements}

        # Load verifies links for requirement artifacts
        verifies_links = self._get_verifies_links_detail(
            req_artifact_ids=req_artifact_ids,
            tenant_id=tenant_id,
        )

        # Build per-requirement test-case map. The Requirement is the link
        # TARGET and the TestCase is the SOURCE (SE `verifies` convention).
        req_testcases: dict[str, list[dict]] = {
            str(r["id"]): [] for r in requirements
        }
        for link_info in verifies_links:
            req_art_id = link_info["req_artifact_id"]
            if req_art_id in req_id_map:
                req_id = req_id_map[req_art_id]
                req_testcases[req_id].append({
                    "id": link_info["testcase_artifact_id"],
                    "result": "Not Run",  # test_result is managed by TestManagement
                })

        entries = [
            RequirementCoverageEntry(
                requirement_id=str(r["id"]),
                test_cases=req_testcases.get(str(r["id"]), []),
            )
            for r in requirements
        ]
        return CoverageData(entries=entries)

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _get_covered_artifact_ids(
        self,
        req_artifact_ids: list[str],
        link_type: str,
        tenant_id: uuid.UUID,
    ) -> set[str]:
        """Return the set of requirement artifact IDs that have a matching link.

        Uses raw SQL for performance with large sets (REQ-L2-TE-012).
        """
        if not req_artifact_ids:
            return set()

        # Build parameterized IN clause.
        # SE link convention (traceability/types.py SE_LINK_SEMANTICS): for a
        # `verifies` link the TestCase is the SOURCE and the Requirement is the
        # TARGET (TC --verifies--> Req). A Requirement is therefore "covered"
        # when its artifact id appears as the link TARGET, not the source.
        placeholders = ", ".join(["%s"] * len(req_artifact_ids))
        sql = f"""
            SELECT DISTINCT target_id
            FROM pl_tracelink
            WHERE target_id IN ({placeholders})
              AND link_type = %s
              AND tenant_id = %s
        """
        params = [*req_artifact_ids, link_type, str(tenant_id)]

        with connection.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

        return {str(row[0]) for row in rows}

    def _get_verifies_links_detail(
        self,
        req_artifact_ids: list[str],
        tenant_id: uuid.UUID,
    ) -> list[dict]:
        """Return verifies-link detail rows for VCRM data building."""
        if not req_artifact_ids:
            return []

        # SE link convention: TestCase is the SOURCE, Requirement the TARGET
        # of a `verifies` link. Select links whose TARGET is a requirement
        # artifact; the SOURCE is then the verifying TestCase.
        placeholders = ", ".join(["%s"] * len(req_artifact_ids))
        sql = f"""
            SELECT source_id, target_id
            FROM pl_tracelink
            WHERE target_id IN ({placeholders})
              AND link_type = 'verifies'
              AND tenant_id = %s
        """
        params = [*req_artifact_ids, str(tenant_id)]

        with connection.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

        return [
            {"testcase_artifact_id": str(row[0]), "req_artifact_id": str(row[1])}
            for row in rows
        ]


__all__ = ["CoverageCalculator"]
