"""
COMP-TE-003 CoverageCalculator — Coverage report tests.

Covers:
  REQ-L2-TE-006: Coverage calculation (verifies links → TestCase)
  REQ-L2-TE-007: Filtered coverage by artifact_type and link_type
  REQ-L2-TE-011: Tenant isolation for coverage queries
"""
from __future__ import annotations

import uuid

import pytest

from traceability.coverage_calculator import CoverageCalculator
from traceability.exceptions import InvalidFilterError
from traceability.tests.conftest import (
    active_tenant,
    make_artifact,
    make_requirement,
    make_test_case,
    make_trace_link,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def calc() -> CoverageCalculator:
    return CoverageCalculator()


# ---------------------------------------------------------------------------
# REQ-L2-TE-006: Coverage calculation
# ---------------------------------------------------------------------------

class TestCoverageCalculation:
    """REQ-L2-TE-006: Test coverage report computation."""

    def test_coverage_7_of_10(self, calc, tenant_a, workspace_a):
        """10 Requirements, 7 with verifies links → 70.0%."""
        with active_tenant(tenant_a):
            req_arts = []
            for i in range(10):
                art, _ = make_requirement(tenant_a, workspace_a, f"Req-{i}")
                req_arts.append(art)

            tc_art, _ = make_test_case(tenant_a, workspace_a, "TC-1")

            # Link first 7 requirements to the test case.
            # SE convention: TestCase is source, Requirement is target.
            for i in range(7):
                make_trace_link(tc_art, req_arts[i], tenant_a, "verifies")

            report = calc.coverage(workspace_a.id)

        assert report.total == 10
        assert report.covered == 7
        assert len(report.uncovered) == 3
        assert report.percentage == 70.0

    def test_coverage_empty_workspace(self, calc, tenant_a, workspace_a):
        """Empty workspace → {total:0, covered:0, uncovered:[], percentage:0.0}."""
        with active_tenant(tenant_a):
            report = calc.coverage(workspace_a.id)

        assert report.total == 0
        assert report.covered == 0
        assert report.uncovered == []
        assert report.percentage == 0.0

    def test_coverage_zero_percent(self, calc, tenant_a, workspace_a):
        """Requirements with no verifies links → 0%."""
        with active_tenant(tenant_a):
            for i in range(5):
                make_requirement(tenant_a, workspace_a, f"Req-{i}")

            report = calc.coverage(workspace_a.id)

        assert report.total == 5
        assert report.covered == 0
        assert report.percentage == 0.0
        assert len(report.uncovered) == 5

    def test_coverage_100_percent(self, calc, tenant_a, workspace_a):
        """All requirements covered → 100.0%."""
        with active_tenant(tenant_a):
            req_arts = []
            for i in range(3):
                art, _ = make_requirement(tenant_a, workspace_a, f"Req-{i}")
                req_arts.append(art)

            tc_art, _ = make_test_case(tenant_a, workspace_a, "TC-1")
            for art in req_arts:
                make_trace_link(tc_art, art, tenant_a, "verifies")

            report = calc.coverage(workspace_a.id)

        assert report.covered == 3
        assert report.percentage == 100.0
        assert report.uncovered == []

    def test_percentage_one_decimal_place(self, calc, tenant_a, workspace_a):
        """Percentage is rounded to 1 decimal place (ADR-L3-TE3-02)."""
        with active_tenant(tenant_a):
            # 1 of 3 = 33.3...%
            req_arts = []
            for i in range(3):
                art, _ = make_requirement(tenant_a, workspace_a, f"Req-{i}")
                req_arts.append(art)

            tc_art, _ = make_test_case(tenant_a, workspace_a, "TC-1")
            make_trace_link(tc_art, req_arts[0], tenant_a, "verifies")

            report = calc.coverage(workspace_a.id)

        assert report.percentage == 33.3

    def test_to_dict_serializable(self, calc, tenant_a, workspace_a):
        """CoverageReport.to_dict() returns correct structure."""
        with active_tenant(tenant_a):
            art, _ = make_requirement(tenant_a, workspace_a, "R1")
            tc_art, _ = make_test_case(tenant_a, workspace_a, "TC-1")
            make_trace_link(tc_art, art, tenant_a, "verifies")

            report = calc.coverage(workspace_a.id)

        d = report.to_dict()
        assert d["total"] == 1
        assert d["covered"] == 1
        assert d["percentage"] == 100.0
        assert isinstance(d["uncovered"], list)


# ---------------------------------------------------------------------------
# REQ-L2-TE-007: Filtered coverage
# ---------------------------------------------------------------------------

class TestFilteredCoverage:
    """REQ-L2-TE-007: Optional artifact_type and link_type filtering."""

    def test_invalid_artifact_type_raises(self, calc, tenant_a, workspace_a):
        """REQ-L2-TE-007: Invalid artifact_type raises InvalidFilterError."""
        with active_tenant(tenant_a):
            with pytest.raises(InvalidFilterError):
                calc.coverage(workspace_a.id, artifact_type="invalid-type")

    def test_custom_link_type_filter(self, calc, tenant_a, workspace_a):
        """REQ-L2-TE-007: Filtering by link_type='satisfies' only counts those links."""
        with active_tenant(tenant_a):
            art_req, _ = make_requirement(tenant_a, workspace_a, "R-A")
            art_arch = make_artifact(tenant_a, workspace_a, "architecture_element")
            # SE convention: ArchitectureElement satisfies Requirement
            # (arch is source, requirement is target).
            make_trace_link(art_arch, art_req, tenant_a, "satisfies")

            # No verifies links → standard coverage is 0
            standard = calc.coverage(workspace_a.id)
            # With satisfies filter → covered = 1
            filtered = calc.coverage(workspace_a.id, link_type="satisfies")

        assert standard.covered == 0
        assert filtered.covered == 1


# ---------------------------------------------------------------------------
# REQ-L2-TE-011: Tenant isolation for coverage
# ---------------------------------------------------------------------------

class TestCoverageIsolation:
    """REQ-L2-TE-011: Coverage report only includes own-tenant links."""

    def test_tenant_isolation_in_coverage(
        self, calc, tenant_a, workspace_a, tenant_b, workspace_b_tenant_b
    ):
        """Tenant-B's coverage report excludes Tenant-A's links."""
        with active_tenant(tenant_a):
            art_req, _ = make_requirement(tenant_a, workspace_a, "R-A")
            tc_art, _ = make_test_case(tenant_a, workspace_a, "TC-A")
            make_trace_link(tc_art, art_req, tenant_a, "verifies")

        # Tenant-B has no requirements
        with active_tenant(tenant_b):
            from persistence.models import Workspace
            ws_b = Workspace.objects.create(tenant=tenant_b, name="ws-cov-b")
            report = calc.coverage(ws_b.id)

        assert report.total == 0


# ---------------------------------------------------------------------------
# get_coverage_data (IF-TE-INT-004)
# ---------------------------------------------------------------------------

class TestGetCoverageData:
    """IF-TE-INT-004: per-requirement test-case data for VCRM."""

    def test_returns_entries_for_all_requirements(
        self, calc, tenant_a, workspace_a
    ):
        """get_coverage_data returns one entry per requirement."""
        with active_tenant(tenant_a):
            for i in range(3):
                make_requirement(tenant_a, workspace_a, f"Req-{i}")

            data = calc.get_coverage_data(workspace_a.id)

        assert len(data.entries) == 3

    def test_requirement_with_verifies_link_has_test_case(
        self, calc, tenant_a, workspace_a
    ):
        """Requirement with verifies link has test_cases populated."""
        with active_tenant(tenant_a):
            art_req, req = make_requirement(tenant_a, workspace_a, "R-1")
            tc_art, tc = make_test_case(tenant_a, workspace_a, "TC-1")
            make_trace_link(tc_art, art_req, tenant_a, "verifies")

            data = calc.get_coverage_data(workspace_a.id)

        entry = next(e for e in data.entries if e.requirement_id == str(req.id))
        assert len(entry.test_cases) == 1
        assert entry.test_cases[0]["id"] == str(tc_art.id)

    def test_empty_workspace_returns_empty_entries(
        self, calc, tenant_a, workspace_a
    ):
        """Empty workspace → CoverageData with empty entries list."""
        with active_tenant(tenant_a):
            data = calc.get_coverage_data(workspace_a.id)

        assert data.entries == []

    def test_test_case_without_run_defaults_to_not_run(
        self, calc, tenant_a, workspace_a
    ):
        """K4: a TestCase with no recorded run reports 'Not Run'."""
        with active_tenant(tenant_a):
            art_req, req = make_requirement(tenant_a, workspace_a, "R-1")
            tc_art, tc = make_test_case(tenant_a, workspace_a, "TC-1")
            make_trace_link(tc_art, art_req, tenant_a, "verifies")

            data = calc.get_coverage_data(workspace_a.id)

        entry = next(e for e in data.entries if e.requirement_id == str(req.id))
        assert entry.test_cases[0]["result"] == "Not Run"

    def test_test_case_result_reflects_latest_testrun_status(
        self, calc, tenant_a, workspace_a
    ):
        """K4: get_coverage_data wires the latest TestRunResult into the VCRM."""
        from datetime import timedelta

        from django.utils import timezone

        from persistence.models import TestRun, TestRunResult

        with active_tenant(tenant_a):
            art_req, req = make_requirement(tenant_a, workspace_a, "R-1")
            tc_art, tc = make_test_case(tenant_a, workspace_a, "TC-1")
            make_trace_link(tc_art, art_req, tenant_a, "verifies")

            run = TestRun.objects.create(
                tenant=tenant_a, workspace=workspace_a, name="Run-1"
            )
            # Older failed result ...
            TestRunResult.objects.create(
                tenant=tenant_a,
                test_run=run,
                test_case=tc,
                test_case_title="TC-1",
                status="failed",
                executed_at=timezone.now() - timedelta(hours=1),
            )
            # ... superseded by a newer passed result.
            TestRunResult.objects.create(
                tenant=tenant_a,
                test_run=run,
                test_case=tc,
                test_case_title="TC-1",
                status="passed",
                executed_at=timezone.now(),
            )

            data = calc.get_coverage_data(workspace_a.id)

        entry = next(e for e in data.entries if e.requirement_id == str(req.id))
        assert entry.test_cases[0]["result"] == "Passed"
