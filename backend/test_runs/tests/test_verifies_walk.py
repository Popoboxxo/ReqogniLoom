"""
Tests for backend.test_runs.services — verifies-chain walk (A.6, REQ-L1-035).

The walk is: TestRun -> TestRunResult -> TestCase -> TraceLink(verifies) -> Requirement.

These tests follow the same pattern as the existing coverage_calculator tests:
real ORM objects + active tenant context. No mocks.
"""
from __future__ import annotations

import pytest

from test_runs.services import get_verified_requirements

from .conftest import (
    active_tenant,
    make_requirement,
    make_test_case,
    make_test_run,
    make_test_run_result,
    make_trace_link,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestGetVerifiedRequirements:
    """REQ-L1-035: 3-hop chain walk TestRun -> Requirement."""

    def test_single_chain_returns_requirement(self, tenant, workspace):
        """One TestRun with one TestCase verifying one Requirement."""
        with active_tenant(tenant):
            req_art, req = make_requirement(tenant, workspace, "REQ-001 Login Flow")
            tc_art, tc = make_test_case(tenant, workspace, "TC-Login")
            make_trace_link(req_art, tc_art, tenant, "verifies")

            tr = make_test_run(tenant, workspace, "CI Run #1")
            make_test_run_result(tenant, tr, tc, status="passed")

            result = get_verified_requirements(tr)

        assert len(result) == 1
        assert result[0].id == req.id
        assert result[0].title == "REQ-001 Login Flow"

    def test_multi_chain_dedupes_requirements(self, tenant, workspace):
        """Two TestCases verifying the same Requirement -> 1 result (deduped)."""
        with active_tenant(tenant):
            req_art, req = make_requirement(tenant, workspace, "REQ-002 Single")
            tc1_art, tc1 = make_test_case(tenant, workspace, "TC-1")
            tc2_art, tc2 = make_test_case(tenant, workspace, "TC-2")
            make_trace_link(req_art, tc1_art, tenant, "verifies")
            make_trace_link(req_art, tc2_art, tenant, "verifies")

            tr = make_test_run(tenant, workspace, "Run #2")
            make_test_run_result(tenant, tr, tc1)
            make_test_run_result(tenant, tr, tc2)

            result = get_verified_requirements(tr)

        assert len(result) == 1
        assert result[0].id == req.id

    def test_multi_chain_distinct_requirements(self, tenant, workspace):
        """Two TestCases verifying two distinct Requirements -> 2 results."""
        with active_tenant(tenant):
            req1_art, req1 = make_requirement(tenant, workspace, "REQ-A")
            req2_art, req2 = make_requirement(tenant, workspace, "REQ-B")
            tc1_art, tc1 = make_test_case(tenant, workspace, "TC-A")
            tc2_art, tc2 = make_test_case(tenant, workspace, "TC-B")
            make_trace_link(req1_art, tc1_art, tenant, "verifies")
            make_trace_link(req2_art, tc2_art, tenant, "verifies")

            tr = make_test_run(tenant, workspace, "Run #3")
            make_test_run_result(tenant, tr, tc1)
            make_test_run_result(tenant, tr, tc2)

            result = get_verified_requirements(tr)

        assert len(result) == 2
        ids = {r.id for r in result}
        assert ids == {req1.id, req2.id}

    def test_no_results_returns_empty(self, tenant, workspace):
        """TestRun with no TestRunResults -> empty list."""
        with active_tenant(tenant):
            tr = make_test_run(tenant, workspace, "Empty Run")
            result = get_verified_requirements(tr)
        assert result == []

    def test_unlinked_test_case_excluded(self, tenant, workspace):
        """TestCase with no verifies TraceLink -> not in result."""
        with active_tenant(tenant):
            req_art, req = make_requirement(tenant, workspace, "REQ-Linked")
            linked_tc_art, linked_tc = make_test_case(tenant, workspace, "TC-Linked")
            unlinked_tc_art, unlinked_tc = make_test_case(tenant, workspace, "TC-Unlinked")
            make_trace_link(req_art, linked_tc_art, tenant, "verifies")

            tr = make_test_run(tenant, workspace, "Mixed")
            make_test_run_result(tenant, tr, linked_tc)
            make_test_run_result(tenant, tr, unlinked_tc)

            result = get_verified_requirements(tr)

        assert len(result) == 1
        assert result[0].id == req.id

    def test_non_verifies_link_excluded(self, tenant, workspace):
        """TraceLink with link_type != 'verifies' must not be picked up."""
        with active_tenant(tenant):
            req_art, req = make_requirement(tenant, workspace, "REQ-V")
            tc_art, tc = make_test_case(tenant, workspace, "TC-V")
            make_trace_link(req_art, tc_art, tenant, "satisfies")  # NOT verifies

            tr = make_test_run(tenant, workspace, "Run NonVerifies")
            make_test_run_result(tenant, tr, tc)

            result = get_verified_requirements(tr)

        assert result == []

    def test_test_case_with_null_fk_returns_empty(self, tenant, workspace):
        """TestRunResult.test_case is null (ON DELETE SET NULL) -> walk safely."""
        with active_tenant(tenant):
            tr = make_test_run(tenant, workspace, "Run Orphan")
            make_test_run_result(tenant, tr, test_case=None, status="not_run")
            result = get_verified_requirements(tr)
        assert result == []
